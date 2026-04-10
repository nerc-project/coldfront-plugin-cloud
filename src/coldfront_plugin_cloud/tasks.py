import datetime
import logging
import time
import functools
from string import Template

from coldfront.core.allocation.models import (
    Allocation,
    AllocationUser,
    AllocationAttribute,
)

from coldfront_plugin_cloud import (
    attributes,
    base,
    openstack,
    openshift,
    esi,
    openshift_vm,
    utils,
    kc_client,
)

logger = logging.getLogger(__name__)


@functools.lru_cache()
def get_kc_client():
    return kc_client.KeyCloakAPIClient()


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
            if allocation.get_attribute(coldfront_attr) is None:
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


def _clean_template_string(template_string: str) -> str:
    return template_string.replace(" ", "_").lower()


def _get_keycloak_group_name(allocation: Allocation, template_string: str) -> str:
    """
    Acceptable variables for the group name template string is:
    - $resource_name: the name of the resource (e.g. "OpenShift")
    - Any allocation attribute defined for the allocation, with spaces replaced by underscores and
    all lowercase (e.g. for `Project Name`, the variable would be `$project_name`)
    """
    resource_name = allocation.resources.first().name
    allocation_attrs_list: list[AllocationAttribute] = (
        allocation.allocationattribute_set.all()
    )

    template_sub_dict = {"resource_name": resource_name}
    for attr in allocation_attrs_list:
        template_sub_dict[
            _clean_template_string(attr.allocation_attribute_type.name)
        ] = attr.value

    return Template(template_string).substitute(**template_sub_dict)


def add_user_to_keycloak(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    kc_admin_client = get_kc_client()
    username = allocation_user.user.username

    group_name_template = allocation.resources.first().get_attribute(
        attributes.RESOURCE_KEYCLOAK_GROUP_TEMPLATE
    )
    if group_name_template is None:
        logger.info(
            f"Keycloak enabled but no group name template specified for resource {allocation.resources.first().name}. Skipping addition to Keycloak group"
        )
        return

    if (user_id := kc_admin_client.get_user_id(username)) is None:
        logger.warning(f"User {username} not found in Keycloak, cannot add to group.")
        return

    group_name = _get_keycloak_group_name(allocation, group_name_template)
    kc_admin_client.create_group(group_name)
    group_id = kc_admin_client.get_group_id(group_name)
    kc_admin_client.add_user_to_group(user_id, group_id)


def remove_user_from_keycloak(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    kc_admin_client = get_kc_client()
    username = allocation_user.user.username

    group_name_template = allocation.resources.first().get_attribute(
        attributes.RESOURCE_KEYCLOAK_GROUP_TEMPLATE
    )
    if group_name_template is None:
        logger.info(
            f"Keycloak enabled but no group name template specified for resource {allocation.resources.first().name}. Skipping removal from Keycloak group"
        )
        return

    if (user_id := kc_admin_client.get_user_id(username)) is None:
        logger.warning(
            f"User {username} not found in Keycloak, cannot remove from group."
        )
        return

    group_name = _get_keycloak_group_name(allocation, group_name_template)
    if (group_id := kc_admin_client.get_group_id(group_name)) is None:
        logger.warning(
            f"Group {group_name} not found in Keycloak, skipping removal for user {username}."
        )
        return
    kc_admin_client.remove_user_from_group(user_id, group_id)
