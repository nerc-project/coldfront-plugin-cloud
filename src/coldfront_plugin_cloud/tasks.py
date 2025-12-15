import datetime
import logging
import time

from coldfront.core.allocation.models import Allocation, AllocationUser

from coldfront_plugin_cloud import (
    attributes,
    base,
    openstack,
    openshift,
    esi,
    openshift_vm,
    utils,
)

logger = logging.getLogger(__name__)


# Map the amount of quota that 1 unit of `quantity` gets you
# This is multiplied to the quantity of that resource allocation.
UNIT_QUOTA_MULTIPLIERS = {
    "openstack": {
        attributes.QUOTA_INSTANCES: 1,
        attributes.QUOTA_VCPU: 1,
        attributes.QUOTA_RAM: 4096,
        attributes.QUOTA_VOLUMES: 2,
        attributes.QUOTA_VOLUMES_GB: 20,
        attributes.QUOTA_FLOATING_IPS: 0,
        attributes.QUOTA_OBJECT_GB: 1,
        attributes.QUOTA_GPU: 0,
    },
    "openshift": {
        attributes.QUOTA_LIMITS_CPU: 1,
        attributes.QUOTA_LIMITS_MEMORY: 4096,
        attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: 5,
        attributes.QUOTA_REQUESTS_NESE_STORAGE: 20,
        attributes.QUOTA_REQUESTS_IBM_STORAGE: 0,
        attributes.QUOTA_REQUESTS_GPU: 0,
        attributes.QUOTA_PVC: 2,
    },
    "openshift_vm": {
        attributes.QUOTA_LIMITS_CPU: 1,
        attributes.QUOTA_LIMITS_MEMORY: 4096,
        attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: 5,
        attributes.QUOTA_REQUESTS_NESE_STORAGE: 20,
        attributes.QUOTA_REQUESTS_IBM_STORAGE: 0,
        attributes.QUOTA_REQUESTS_VM_GPU_A100_SXM4: 0,
        attributes.QUOTA_REQUESTS_VM_GPU_V100: 0,
        attributes.QUOTA_REQUESTS_VM_GPU_H100: 0,
        attributes.QUOTA_PVC: 2,
    },
    "esi": {attributes.QUOTA_FLOATING_IPS: 0, attributes.QUOTA_NETWORKS: 0},
}

# The amount of quota that every projects gets,
# regardless of units of quantity. This is added
# on top of the multiplication.
STATIC_QUOTA = {
    "openstack": {
        attributes.QUOTA_FLOATING_IPS: 2,
        attributes.QUOTA_GPU: 0,
    },
    "openshift": {
        attributes.QUOTA_REQUESTS_GPU: 0,
    },
    "esi": {attributes.QUOTA_FLOATING_IPS: 1, attributes.QUOTA_NETWORKS: 1},
    "openshift_vm": {
        attributes.QUOTA_REQUESTS_VM_GPU_A100_SXM4: 0,
        attributes.QUOTA_REQUESTS_VM_GPU_V100: 0,
        attributes.QUOTA_REQUESTS_VM_GPU_H100: 0,
    },
}


def get_expected_attributes(allocator: base.ResourceAllocator):
    """Based on the allocator's resource type, return the expected quotas attributes the allocation should have"""
    resource_name = allocator.resource_type
    resource_expected_quotas = UNIT_QUOTA_MULTIPLIERS[resource_name].copy()

    # If the resource attribute is not set (i.e for OpenStack resources), get_attribute returns None
    is_ibm_storage_available = allocator.resource.get_attribute(
        attributes.RESOURCE_IBM_AVAILABLE
    )
    is_ibm_storage_available = (
        is_ibm_storage_available and is_ibm_storage_available.lower() == "true"
    )
    if "openshift" in resource_name and not is_ibm_storage_available:
        resource_expected_quotas.pop(
            attributes.QUOTA_REQUESTS_IBM_STORAGE, None
        )  # The resource may or may not already have this attribute

    return list(resource_expected_quotas.keys())


def find_allocator(allocation) -> base.ResourceAllocator:
    allocators = {
        "openstack": openstack.OpenStackResourceAllocator,
        "openshift": openshift.OpenShiftResourceAllocator,
        "esi": esi.ESIResourceAllocator,
        "openshift virtualization": openshift_vm.OpenShiftVMResourceAllocator,
    }
    # TODO(knikolla): It doesn't seem to be possible to select multiple resources
    # when requesting a new allocation, so why is this multivalued?
    # Does it have to do with linked resources?
    resource = allocation.resources.first()
    if allocator_class := allocators.get(resource.resource_type.name.lower()):
        return allocator_class(resource, allocation)


def activate_allocation(allocation_pk):
    def set_quota_attributes():
        if allocation.quantity < 1:
            # This could lead to negative values which can be interpreted as no quota
            allocation.quantity = 1

        # Calculate the quota for the project, and set the attribute for each element
        expected_coldfront_attrs = get_expected_attributes(allocator)
        for coldfront_attr in expected_coldfront_attrs:
            if not allocation.get_attribute(coldfront_attr):
                value = allocation.quantity * UNIT_QUOTA_MULTIPLIERS[
                    allocator.resource_type
                ].get(coldfront_attr, 0)
                value += STATIC_QUOTA[allocator.resource_type].get(coldfront_attr, 0)
                utils.set_attribute_on_allocation(allocation, coldfront_attr, value)

    allocation = Allocation.objects.get(pk=allocation_pk)

    if allocator := find_allocator(allocation):
        if project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            allocator.reactivate_project(project_id)
        else:
            project = allocator.create_project(allocation.project.title)

            project_id = project.id
            project_name = project.name

            utils.set_attribute_on_allocation(
                allocation, attributes.ALLOCATION_PROJECT_NAME, project_name
            )
            utils.set_attribute_on_allocation(
                allocation, attributes.ALLOCATION_PROJECT_ID, project_id
            )
            utils.set_attribute_on_allocation(
                allocation, attributes.ALLOCATION_INSTITUTION_SPECIFIC_CODE, "N/A"
            )
            set_quota_attributes()

            allocator.create_project_defaults(project_id)

        pi_username = allocation.project.pi.username
        allocator.get_or_create_federated_user(pi_username)
        allocator.assign_role_on_user(pi_username, project_id)

        allocator.set_quota(project_id)


def disable_allocation(allocation_pk):
    allocation = Allocation.objects.get(pk=allocation_pk)

    if allocator := find_allocator(allocation):
        if project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            allocator.disable_project(project_id)
        else:
            logger.warning("No project has been created. Nothing to disable.")


def add_user_to_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    if allocator := find_allocator(allocation):
        username = allocation_user.user.username

        # Note(knikolla): This task may be executed at the same time as
        # activating an allocation, therefore it has to wait for the project
        # to finish creating. Maximum wait is 2 minutes.
        time_start = datetime.datetime.utcnow()
        max_wait_seconds = 120

        while not (
            project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        ):
            delta = datetime.datetime.utcnow() - time_start
            if delta.seconds >= max_wait_seconds:
                raise Exception(
                    f"Project not yet created after {delta.seconds} seconds."
                )

            logging.info(
                f"Project not created yet, waiting. "
                f"(Elapsed {delta.seconds}/{max_wait_seconds} seconds.)"
            )
            time.sleep(2)

        allocator.get_or_create_federated_user(username)
        allocator.assign_role_on_user(username, project_id)


def remove_user_from_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    if allocator := find_allocator(allocation):
        if project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            username = allocation_user.user.username
            allocator.remove_role_from_user(username, project_id)
        else:
            logger.warning("No project has been created. Nothing to disable.")
