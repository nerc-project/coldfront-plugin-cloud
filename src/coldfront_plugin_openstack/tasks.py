import datetime
import logging
import secrets
import time

from coldfront.core.allocation.models import (Allocation,
                                              AllocationUser)
from keystoneclient.v3 import client

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


def get_or_create_federated_user(resource, username):
    if not (user := openstack.get_federated_user(resource, username)):
        user = openstack.create_federated_user(resource, username)
    return user


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
        if project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            openstack.reactivate_project(resource, project_id)
        else:
            project_name = get_unique_project_name(allocation.project.title)
            project_id = openstack.create_project(resource, project_name)

            utils.set_attribute_on_allocation(allocation,
                                              attributes.ALLOCATION_PROJECT_NAME,
                                              project_name)
            utils.set_attribute_on_allocation(allocation,
                                              attributes.ALLOCATION_PROJECT_ID,
                                              project_id)
            set_quota_attributes()

            openstack.create_project_defaults(resource, allocation, project_id)

        pi_username = allocation.project.pi.username
        get_or_create_federated_user(resource, pi_username)
        openstack.assign_role_on_user(resource, pi_username, project_id)

        openstack.set_quota(resource, allocation)


def disable_allocation(allocation_pk):
    allocation = Allocation.objects.get(pk=allocation_pk)

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        if project_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            openstack.disable_project(project_id)
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

        get_or_create_federated_user(resource, username)
        openstack.assign_role_on_user(resource, username, project_id)


def remove_user_from_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        identity = client.Client(
            session=openstack.get_session_for_resource(resource)
        )

        username = allocation_user.user.username

        if user := openstack.get_federated_user(resource, username):
            role_name = resource.get_attribute(attributes.RESOURCE_ROLE) or 'member'
            role = identity.roles.find(name=role_name)
            project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

            identity.roles.revoke(user=user['id'], project=project_id, role=role)
