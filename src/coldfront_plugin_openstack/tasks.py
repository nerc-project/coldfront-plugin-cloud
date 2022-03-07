import datetime
import logging
import secrets
import time
import urllib.parse

from coldfront.core.allocation.models import (Allocation,
                                              AllocationUser)
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneauth1 import exceptions as ksa_exceptions
from keystoneclient.v3 import client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient

from coldfront_plugin_openstack import attributes, openstack, utils

logger = logging.getLogger(__name__)

# Map the attribute name in ColdFront, to the client of the respective
# service, the version of the API, and the key in the payload.
QUOTA_KEY_MAPPING = {
    'compute': {
        'class': novaclient.Client,
        'version': 2,
        'keys': {
            attributes.QUOTA_INSTANCES: 'instances',
            attributes.QUOTA_VCPU: 'cores',
            attributes.QUOTA_RAM: 'ram',
        },
    },
    'volume': {
        'class': cinderclient.Client,
        'version': 3,
        'keys': {
            attributes.QUOTA_VOLUMES: 'volumes',
            attributes.QUOTA_VOLUMES_GB: 'gigabytes',
        }
    },
    'network': {
        'class': neutronclient.Client,
        'version': None,
        'keys': {
            attributes.QUOTA_FLOATING_IPS: 'floatingip'
        }
    }
}

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
    def set_quota():
        # If an attribute with the appropriate name is associated with an
        # allocation, set that as the quota. Otherwise, multiply
        # the quantity attribute via the mapping table above.
        for service_name, service in QUOTA_KEY_MAPPING.items():
            client = service['class'](
                version=service['version'],
                session=openstack.get_session_for_resource(resource)
            )
            payload = dict()
            for coldfront_attr, openstack_key in service['keys'].items():
                if value := allocation.get_attribute(coldfront_attr):
                    pass
                else:
                    value = allocation.quantity * UNIT_QUOTA_MULTIPLIERS.get(coldfront_attr, 0)
                    value = value + STATIC_QUOTA.get(coldfront_attr, 0)
                    utils.set_attribute_on_allocation(allocation,
                                                      coldfront_attr,
                                                      value)
                payload[openstack_key] = value

                if service_name == 'network':
                    # The neutronclient call for quotas is slightly different
                    # from how the other clients do it.
                    client.update_quota(openstack_project.id, body={'quota': payload})
                else:
                    client.quotas.update(openstack_project.id, **payload)

    allocation = Allocation.objects.get(pk=allocation_pk)

    # TODO(knikolla): It doesn't seem to be possible to select multiple resources
    # when requesting a new allocation, so why is this multivalued?
    # Does it have to do with linked resources?
    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        if allocation.quantity < 1:
            # This could lead to negative values which can be interpreted as no quota
            allocation.quantity = 1

        identity = client.Client(
            session=openstack.get_session_for_resource(resource)
        )

        if existing_id := allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID):
            openstack_project = identity.projects.get(existing_id)
            openstack_project.update(enabled=True)
        else:
            openstack_project_name = get_unique_project_name(allocation.project.title)
            openstack_project = identity.projects.create(
                name=openstack_project_name,
                domain=resource.get_attribute(attributes.RESOURCE_PROJECT_DOMAIN),
                enabled=True,
            )

            utils.set_attribute_on_allocation(allocation,
                                              attributes.ALLOCATION_PROJECT_NAME,
                                              openstack_project_name)
            utils.set_attribute_on_allocation(allocation,
                                              attributes.ALLOCATION_PROJECT_ID,
                                              openstack_project.id)

            if resource.get_attribute(attributes.RESOURCE_DEFAULT_PUBLIC_NETWORK):
                logger.info(f'Creating default network for project '
                            f'{openstack_project.id}.')
                openstack.create_default_network(resource, openstack_project.id)
            else:
                logger.info(f'No public network configured. Skipping default '
                            f'network creation for project {openstack_project.id}.')

        pi_username = allocation.project.pi.username
        get_or_create_federated_user(resource, pi_username)
        openstack.assign_role_on_user(
            resource, pi_username,
            allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        )

        set_quota()


def disable_allocation(allocation_pk):
    allocation = Allocation.objects.get(pk=allocation_pk)

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        ksa_session = openstack.get_session_for_resource(resource)
        identity = client.Client(session=ksa_session)

        identity.projects.update(allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID),
                                 enabled=False)


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
