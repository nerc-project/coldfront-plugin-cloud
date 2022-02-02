import logging
import os
import secrets
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

from coldfront_plugin_openstack import (attributes,
                                        utils)

logger = logging.getLogger(__name__)

NOVA_VERSION = '2'
NOVA_KEY_MAPPING = {
    attributes.QUOTA_INSTANCES: 'instances',
    attributes.QUOTA_VCPU: 'cores',
    attributes.QUOTA_RAM: 'ram',
}

CINDER_VERSION = '3'
CINDER_KEY_MAPPING = {
    attributes.QUOTA_VOLUMES: 'volumes',
    attributes.QUOTA_VOLUMES_GB: 'gigabytes',
}

UNIT_TO_QUOTA_MAPPING = {
    attributes.QUOTA_INSTANCES: 1,
    attributes.QUOTA_VCPU: 2,
    attributes.QUOTA_RAM: 4096,
    attributes.QUOTA_VOLUMES: 2,
    attributes.QUOTA_VOLUMES_GB: 100,
}


def is_openstack_resource(resource):
    return resource.resource_type.name.lower() == 'openstack'


def get_unique_project_name(project_name):
    return f'{project_name}-f{secrets.token_hex(3)}'


def get_session_for_resource(resource):
    auth_url = resource.get_attribute(attributes.RESOURCE_AUTH_URL)
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
    return session.Session(
        auth,
        verify=os.environ.get('FUNCTIONAL_TESTS', '') != 'True'
    )


def get_user_payload_for_resource(resource, username):
    domain_id = resource.get_attribute(attributes.RESOURCE_USER_DOMAIN)
    idp_id = resource.get_attribute(attributes.RESOURCE_IDP)
    protocol = resource.get_attribute(attributes.RESOURCE_FEDERATION_PROTOCOL) or 'openid'
    return {
        'user': {
            'domain_id': domain_id,
            'enabled': True,
            'name': username,
            'email': username,
            'federated': [
                {
                    'idp_id': idp_id,
                    'protocols': [
                        {
                            'protocol_id': protocol,
                            'unique_id': urllib.parse.quote_plus(username)
                        }
                    ]
                }
            ]
        }
    }


def get_federated_user(resource, username):
    # Query by unique_id
    query_response = get_session_for_resource(resource).get(
        f'{resource.get_attribute(attributes.RESOURCE_AUTH_URL)}/v3/users?unique_id={username}'
    ).json()
    if query_response['users']:
        return query_response['users'][0]

    # Query by name as a fallback (this might return a non-federated user)
    query_response = get_session_for_resource(resource).get(
        f'{resource.get_attribute(attributes.RESOURCE_AUTH_URL)}/v3/users?'
        f'name={username}&domain_id={resource.get_attribute(attributes.RESOURCE_USER_DOMAIN)}'
    ).json()
    if query_response['users']:
        return query_response['users'][0]


def create_federated_user(resource, unique_id):
    create_response = get_session_for_resource(resource).post(
        f'{resource.get_attribute(attributes.RESOURCE_AUTH_URL)}/v3/users',
        json=get_user_payload_for_resource(resource, unique_id)
    )
    if create_response.ok:
        return create_response.json()['user']


def get_or_create_federated_user(resource, username):
    if not (user := get_federated_user(resource, username)):
        user = create_federated_user(resource, username)
    return user


def assign_role_on_user(resource, username, project_id):
    role_name = resource.get_attribute(attributes.RESOURCE_ROLE) or 'member'

    ksa_session = get_session_for_resource(resource)
    identity = client.Client(session=ksa_session)
    role = identity.roles.find(name=role_name)

    user = get_federated_user(resource, username)
    identity.roles.grant(user=user['id'], project=project_id, role=role)


def create_default_network(resource, project_id):
    neutron = neutronclient.Client(session=get_session_for_resource(resource))

    # Get or create default network
    networks = neutron.list_networks(project_id=project_id,
                                     name='default_network')
    if networks := networks['networks']:
        network = networks[0]
        logger.info(f'Default network with ID {network["network"]["id"]} '
                    f'already exists for project {project_id}.')
    else:
        default_network_payload = {
            'network': {
                'name': 'default_network',
                'project_id': project_id,
                'admin_state_up': True,
                'description': 'Default network created during provisioning.',
            }
        }
        network = neutron.create_network(body=default_network_payload)
        logger.info(f'Default network with ID {network["network"]["id"]} '
                    f'created for project {project_id}.')

    # Get or create default subnet
    subnets = neutron.list_subnets(project_id=project_id,
                                   name='default_subnet')
    if subnets := subnets['subnets']:
        subnet = subnets[0]
        logger.info(f'Default subnet with ID {subnet["subnet"]["id"]} '
                    f'already exists for project {project_id}.')
    else:
        default_subnet_payload = {
            'subnet': {
                'network_id': network['network']['id'],
                'name': 'default_subnet',
                'ip_version': 4,
                'project_id': project_id,
                'cidr': resource.get_attribute(
                    attributes.RESOURCE_DEFAULT_NETWORK_CIDR) or '192.168.0.0/24',
                'dns_nameservers': ['8.8.8.8', '8.8.4.4'],
                'description': 'Default subnet created during provisioning.',
            }
        }
        subnet = neutron.create_subnet(body=default_subnet_payload)
        logger.info(f'Default subnet with ID {subnet["subnet"]["id"]} '
                    f'created for project {project_id}.')

    # Get or create default router
    routers = neutron.list_routers(project_id=project_id,
                                   name='default_router')
    if routers := routers['routers']:
        router = routers[0]
    else:
        default_router_payload = {
            'router': {
                'name': 'default_router',
                'external_gateway_info': {
                    "network_id": resource.get_attribute(
                        attributes.RESOURCE_DEFAULT_PUBLIC_NETWORK)
                },
                'project_id': project_id,
                'admin_state_up': True,
                'description': 'Default router created during provisioning.'
            }
        }
        router = neutron.create_router(body=default_router_payload)

    # Get or create port on router
    router_id = router['router']['id']
    network_id = network['network']['id']
    subnet_id = subnet['subnet']['id']

    ports = neutron.list_ports(project_id=project_id,
                               device_id=router_id,
                               network_id=network_id)
    if ports['ports']:
        logger.info(f'Router {router_id} already connected to network {network_id} for '
                    f'project {project_id}.')
    else:
        default_interface_payload = {'subnet_id': subnet_id}
        neutron.add_interface_router(router_id,
                                     body=default_interface_payload)
        logger.info(f'Router {router_id} connected to subnet {subnet_id} for '
                    f'project {project_id}.')


def activate_allocation(allocation_pk):
    def set_nova_quota():
        compute = novaclient.Client(NOVA_VERSION, session=get_session_for_resource(resource))
        # If an attribute with the appropriate name is associated with an
        # allocation, set that as the quota. Otherwise, multiply
        # the quantity attribute via the mapping table above.
        nova_payload = {
            nova_key: allocation.get_attribute(key)
            if allocation.get_attribute(key) else allocation.quantity * UNIT_TO_QUOTA_MAPPING[key]
            for (key, nova_key) in NOVA_KEY_MAPPING.items()
        }
        compute.quotas.update(openstack_project.id, **nova_payload)

    def set_cinder_quota():
        storage = cinderclient.Client(CINDER_VERSION,
                                      session=get_session_for_resource(resource))
        cinder_payload = {
            cinder_key: allocation.get_attribute(key)
            if allocation.get_attribute(key) else allocation.quantity * UNIT_TO_QUOTA_MAPPING[key]
            for (key,cinder_key) in CINDER_KEY_MAPPING.items()
        }
        storage.quotas.update(openstack_project.id, **cinder_payload)

    allocation = Allocation.objects.get(pk=allocation_pk)

    # TODO(knikolla): It doesn't seem to be possible to select multiple resources
    # when requesting a new allocation, so why is this multivalued?
    # Does it have to do with linked resources?
    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        if allocation.quantity < 1:
            # This could lead to negative values which can be interpreted as no quota
            allocation.quantity = 1

        identity = client.Client(session=get_session_for_resource(resource))

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

            utils.add_attribute_to_allocation(allocation,
                                              attributes.ALLOCATION_PROJECT_NAME,
                                              openstack_project_name)
            utils.add_attribute_to_allocation(allocation,
                                              attributes.ALLOCATION_PROJECT_ID,
                                              openstack_project.id)

            if resource.get_attribute(attributes.RESOURCE_DEFAULT_PUBLIC_NETWORK):
                logger.info(f'Creating default network for project '
                            f'{openstack_project.id}.')
                create_default_network(resource, openstack_project.id)
            else:
                logger.info(f'No public network configured. Skipping default '
                            f'network creation for project {openstack_project.id}.')

        pi_username = allocation.project.pi.username
        get_or_create_federated_user(resource, pi_username)
        assign_role_on_user(resource, pi_username,
                            allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID))

        set_nova_quota()
        set_cinder_quota()


def disable_allocation(allocation_pk):
    allocation = Allocation.objects.get(pk=allocation_pk)

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        ksa_session = get_session_for_resource(resource)
        identity = client.Client(session=ksa_session)

        identity.projects.update(allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID),
                                 enabled=False)


def add_user_to_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    resource = allocation.resources.first()
    if is_openstack_resource(resource):

        username = allocation_user.user.username
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        if not project_id:
            raise Exception('Project not created yet!')

    get_or_create_federated_user(resource, username)
    assign_role_on_user(resource, username, project_id)


def remove_user_from_allocation(allocation_user_pk):
    allocation_user = AllocationUser.objects.get(pk=allocation_user_pk)
    allocation = allocation_user.allocation

    resource = allocation.resources.first()
    if is_openstack_resource(resource):
        identity = client.Client(session=get_session_for_resource(resource))

        username = allocation_user.user.username

        if user := get_federated_user(resource, username):
            role_name = resource.get_attribute(attributes.RESOURCE_ROLE) or 'member'
            role = identity.roles.find(name=role_name)
            project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

            identity.roles.revoke(user=user['id'], project=project_id, role=role)
