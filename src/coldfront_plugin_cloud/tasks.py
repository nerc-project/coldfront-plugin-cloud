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
        resource_quotaspecs = allocator.resource_quotaspecs
        for coldfront_attr, quota_spec in resource_quotaspecs.root.items():
            if not allocation.get_attribute(coldfront_attr):
                value = quota_spec.quota_by_su_quantity(allocation.quantity)
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
