import datetime
import logging
import secrets
import time

from coldfront.core.allocation.models import (Allocation,
                                              AllocationUser)

from coldfront_plugin_openstack import attributes, openstack, utils

logger = logging.getLogger(__name__)


# Map the amount of quota that 1 unit of `quantity` gets you
# This is multiplied to the quantity of that resource allocation.
UNIT_QUOTA_MULTIPLIERS = {
    attributes.QUOTA_INSTANCES: 1,
    attributes.QUOTA_VCPU: 2,
    attributes.QUOTA_RAM: 4096,
    attributes.QUOTA_VOLUMES: 2,
    attributes.QUOTA_VOLUMES_GB: 100,
    attributes.QUOTA_FLOATING_IPS: 0,
}

# The amount of quota that every projects gets,
# regardless of units of quantity. This is added
# on top of the multiplication.
STATIC_QUOTA = {
    attributes.QUOTA_FLOATING_IPS: 2,
}


def is_openstack_resource(resource):
    return resource.resource_type.name.lower() == 'openstack'


def get_unique_project_name(project_name):
    return f'{project_name}-f{secrets.token_hex(3)}'


def activate_allocation(allocation_pk):
    def set_quota_attributes():
        if allocation.quantity < 1:
            # This could lead to negative values which can be interpreted as no quota
            allocation.quantity = 1

        # Calculate the quota for the project, and set the attribute for each element
        for coldfront_attr in UNIT_QUOTA_MULTIPLIERS.keys():
            if not allocation.get_attribute(coldfront_attr):
                value = allocation.quantity * UNIT_QUOTA_MULTIPLIERS.get(coldfront_attr, 0)
                value = value + STATIC_QUOTA.get(coldfront_attr, 0)
                utils.set_attribute_on_allocation(allocation,
                                                  coldfront_attr,
                                                  value)

    allocation = Allocation.objects.get(pk=allocation_pk)

    # TODO(knikolla): It doesn't seem to be possible to select multiple resources
    # when requesting a new allocation, so why is this multivalued?
    # Does it have to do with linked resources?
    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        allocator = openstack.OpenStackResourceAllocator(resource,
                                                         allocation)

        if project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            allocator.reactivate_project(project_id)
        else:
            project_name = get_unique_project_name(allocation.project.title)
            project_id = allocator.create_project(project_name)

            utils.set_attribute_on_allocation(allocation,
                                              attributes.ALLOCATION_PROJECT_NAME,
                                              project_name)
            utils.set_attribute_on_allocation(allocation,
                                              attributes.ALLOCATION_PROJECT_ID,
                                              project_id)
            set_quota_attributes()

            allocator.create_project_defaults(project_id)

        pi_username = allocation.project.pi.username
        allocator.get_or_create_federated_user(pi_username)
        allocator.assign_role_on_user(pi_username, project_id)

        allocator.set_quota(project_id)


def disable_allocation(allocation_pk):
    allocation = Allocation.objects.get(pk=allocation_pk)

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        if project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            allocator = openstack.OpenStackResourceAllocator(resource,
                                                             allocation)
            allocator.disable_project(project_id)
        else:
            logger.warning('No project has been created. Nothing to disable.')


def add_user_to_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
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
                raise Exception(f'Project not yet created after {delta.seconds} seconds.')

            logging.info(
                f'Project not created yet, waiting. '
                f'(Elapsed {delta.seconds}/{max_wait_seconds} seconds.)'
            )
            time.sleep(2)

        allocator = openstack.OpenStackResourceAllocator(resource,
                                                         allocation)
        allocator.get_or_create_federated_user(username)
        allocator.assign_role_on_user(username, project_id)


def remove_user_from_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        if project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            allocator = openstack.OpenStackResourceAllocator(resource,
                                                             allocation)
            username = allocation_user.user.username
            allocator.remove_role_from_user(username, project_id)
        else:
            logger.warning('No project has been created. Nothing to disable.')
