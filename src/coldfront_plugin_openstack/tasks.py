import os
import secrets

from coldfront.core.allocation.models import (Allocation,
                                              AllocationUser)
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient

from coldfront_plugin_openstack import utils

ALLOCATION_ATTR_PROJECT_ID = 'OpenStack Project ID'
ALLOCATION_ATTR_PROJECT_NAME = 'OpenStack Project Name'

RESOURCE_ATTR_AUTH_URL = 'OpenStack Auth URL'
RESOURCE_ATTR_FEDERATION_PROTOCOL = 'OpenStack Federation Protocol'
RESOURCE_ATTR_IDP = 'OpenStack Identity Provider'
RESOURCE_ATTR_PROJECT_DOMAIN = 'OpenStack Domain for Projects'
RESOURCE_ATTR_ROLE = 'OpenStack Role for User in Project'
RESOURCE_ATTR_USER_DOMAIN = 'OpenStack Domain for Users'

NOVA_VERSION = '2'
# Mapping of allocation attribute name for Quota, and what Nova expects
# TODO: Move the magic strings into global variables
NOVA_KEY_MAPPING = {
    'OpenStack Compute Instance Quota': 'instances',
    'OpenStack Compute vCPU Quota': 'cores',
    'OpenStack Compute RAM Quota': 'ram',
}

UNIT_TO_QUOTA_MAPPING = {
    'OpenStack Compute Instance Quota': 1,
    'OpenStack Compute vCPU Quota': 2,
    'OpenStack Compute RAM Quota': 4096,
    'OpenStack Volumes': 1,
}


def is_openstack_resource(resource):
    return resource.resource_type.name.lower() == 'openstack'


def get_unique_project_name(project_name):
    return f'{project_name}-f{secrets.token_hex(3)}'


def get_session_for_resource(resource):
    auth_url = resource.get_attribute(RESOURCE_ATTR_AUTH_URL)
    # Note: Authentication for a specific OpenStack cloud is stored in env
    # variables of the form OPENSTACK_{RESOURCE_NAME}_APPLICATION_CREDENTIAL_ID
    # and OPENSTACK_{RESOURCE_NAME}_APPLICATION_CREDENTIAL_SECRET
    # where resource name is has spaces replaced with underscored and is
    # uppercase.
    # This allows for the possibility of managing multiple OpenStack clouds
    # via multiple resources.
    var_name = resource.name.replace(' ', '_').replace('-', '_').upper()
    auth = v3.ApplicationCredential(
        auth_url=auth_url,
        application_credential_id=os.environ.get(
            f'OPENSTACK_{var_name}_APPLICATION_CREDENTIAL_ID'),
        application_credential_secret=os.environ.get(
            f'OPENSTACK_{var_name}_APPLICATION_CREDENTIAL_SECRET')
    )
    return session.Session(auth)


def get_user_payload_for_resource(username, resource):
    domain_id = resource.get_attribute(RESOURCE_ATTR_USER_DOMAIN)
    idp_id = resource.get_attribute(RESOURCE_ATTR_IDP)
    protocol = resource.get_attribute(RESOURCE_ATTR_FEDERATION_PROTOCOL) or 'openid'
    return {
        'user': {
            'domain_id': domain_id,
            'enabled': True,
            'name': username,
            'federated': [
                {
                    'idp_id': idp_id,
                    'protocols': [
                        {
                            'protocol_id': protocol,
                            'unique_id': username
                        }
                    ]
                }
            ]
        }
    }


def activate_allocation(allocation_pk):
    def set_nova_quota():
        compute = novaclient.Client(NOVA_VERSION, session=ksa_session)
        # If an attribute with the appropriate name is associated with an
        # allocation, set that as the quota. Otherwise, multiply
        # the quantity attribute via the mapping table above.
        nova_payload = {
            nova_key: allocation.get_attribute(key)
            if allocation.get_attribute(key) else allocation.quantity * UNIT_TO_QUOTA_MAPPING[key]
            for (key, nova_key) in NOVA_KEY_MAPPING.items()
        }
        compute.quotas.update(openstack_project.id, **nova_payload)

    allocation = Allocation.objects.get(pk=allocation_pk)

    # TODO(knikolla): It doesn't seem to be possible to select multiple resources
    # when requesting a new allocation, so why is this multivalued?
    # Does it have to do with linked resources?
    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        if allocation.quantity < 1:
            # This could lead to negative values which can be interpreted as no quota
            allocation.quantity = 1

        ksa_session = get_session_for_resource(resource)
        identity = client.Client(session=ksa_session)

        # TODO: There is a possibility that this is a reactivation, rather than a new allocation
        openstack_project_name = get_unique_project_name(allocation.project.title)
        openstack_project = identity.projects.create(
            name=openstack_project_name,
            domain=resource.get_attribute(RESOURCE_ATTR_PROJECT_DOMAIN),
            enabled=True,
        )

        utils.add_attribute_to_allocation(allocation,
                                          ALLOCATION_ATTR_PROJECT_NAME,
                                          openstack_project_name)
        utils.add_attribute_to_allocation(allocation,
                                          ALLOCATION_ATTR_PROJECT_ID,
                                          openstack_project.id)

        set_nova_quota()


def disable_allocation(allocation_pk):
    allocation = Allocation.objects.get(pk=allocation_pk)

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        ksa_session = get_session_for_resource(resource)
        identity = client.Client(session=ksa_session)

        identity.projects.update(allocation.get_attribute(ALLOCATION_ATTR_PROJECT_ID),
                                 enabled=False)


def add_user_to_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        ksa_session = get_session_for_resource(resource)
        identity = client.Client(session=ksa_session)

        username = allocation_user.user.username
        project_id = allocation.get_attribute(ALLOCATION_ATTR_PROJECT_ID)
        if not project_id:
            raise Exception('Project not created yet!')

        role_name = resource.get_attribute(RESOURCE_ATTR_ROLE) or 'member'

        user_id = None
        query_response = ksa_session.get(
            f'{resource.get_attribute(RESOURCE_ATTR_AUTH_URL)}/v3/users?unique_id={username}'
        ).json()
        if query_response['users']:
            user_id = query_response['users'][0]['id']
        else:
            create_response = ksa_session.post(
                f'{resource.get_attribute(RESOURCE_ATTR_AUTH_URL)}/v3/users',
                json=get_user_payload_for_resource(username, resource)
            )
            if create_response.ok:
                user_id = create_response.json()['user']['id']

        if not user_id:
            raise Exception('User was not created.')

        role = identity.roles.find(name=role_name)
        identity.roles.grant(user=user_id, project=project_id, role=role)


def remove_user_from_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        ksa_session = get_session_for_resource(resource)
        identity = client.Client(session=ksa_session)

        username = allocation_user.user.username

        query_response = ksa_session.get(
            f'{resource.get_attribute(RESOURCE_ATTR_AUTH_URL)}/v3/users?unique_id={username}'
        ).json()
        if query_response['users']:
            user_id = query_response['users'][0]['id']

            role_name = resource.get_attribute(RESOURCE_ATTR_ROLE) or 'member'
            role = identity.roles.find(name=role_name)
            project_id = allocation.get_attribute(ALLOCATION_ATTR_PROJECT_ID)

            identity.roles.revoke(user=user_id, project=project_id, role=role)
