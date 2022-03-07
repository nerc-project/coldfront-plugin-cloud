import logging
import os
import urllib.parse

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneauth1 import exceptions as ksa_exceptions
from keystoneclient.v3 import client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient

from coldfront_plugin_openstack import attributes

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


def create_project(resource, project_name) -> str:
    identity = client.Client(
        session=get_session_for_resource(resource)
    )
    openstack_project = identity.projects.create(
        name=project_name,
        domain=resource.get_attribute(attributes.RESOURCE_PROJECT_DOMAIN),
        enabled=True,
    )
    return openstack_project.id


def reactivate_project(resource, project_id):
    identity = client.Client(
        session=get_session_for_resource(resource)
    )
    openstack_project = identity.projects.get(project_id)
    openstack_project.update(enabled=True)


def set_quota(resource, allocation):
    project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

    # If an attribute with the appropriate name is associated with an
    # allocation, set that as the quota. Otherwise, multiply
    # the quantity attribute via the mapping table above.
    for service_name, service in QUOTA_KEY_MAPPING.items():
        client = service['class'](
            version=service['version'],
            session=get_session_for_resource(resource)
        )

        # No need to do any calculations here, just go through each service
        # and set the value in the attribute.
        payload = dict()
        for coldfront_attr, openstack_key in service['keys'].items():
            payload[openstack_key] = allocation.get_attribute(coldfront_attr)

        if service_name == 'network':
            # The neutronclient call for quotas is slightly different
            # from how the other clients do it.
            client.update_quota(project_id, body={'quota': payload})
        else:
            client.quotas.update(project_id, **payload)


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


def create_project_defaults(resource, allocation, project_id):
    if resource.get_attribute(attributes.RESOURCE_DEFAULT_PUBLIC_NETWORK):
        logger.info(f'Creating default network for project '
                    f'{project_id}.')
        create_default_network(
            resource, allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        )
    else:
        logger.info(f'No public network configured. Skipping default '
                    f'network creation for project {project_id}.')
