import functools
import logging
import os
import urllib.parse

import swiftclient
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneauth1 import exceptions as ksa_exceptions
from keystoneclient.v3 import client as ks_client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient

from coldfront_plugin_openstack import attributes, base, utils

logger = logging.getLogger(__name__)


# Map the attribute name in ColdFront, to the client of the respective
# service, the version of the API, and the key in the payload.
QUOTA_KEY_MAPPING = {
    'compute': {
        'keys': {
            attributes.QUOTA_INSTANCES: 'instances',
            attributes.QUOTA_VCPU: 'cores',
            attributes.QUOTA_RAM: 'ram',
        },
    },
    'network': {
        'keys': {
            attributes.QUOTA_FLOATING_IPS: 'floatingip',
        }
    },
    'object': {
        'keys': {
            attributes.QUOTA_OBJECT_GB: 'X-Account-Meta-Quota-Bytes',
        }
    },
    'volume': {
        'keys': {
            attributes.QUOTA_VOLUMES: 'volumes',
            attributes.QUOTA_VOLUMES_GB: 'gigabytes',
        }
    },
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
    var_name = utils.env_safe_name(resource.name)
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


class OpenStackResourceAllocator(base.ResourceAllocator):

    resource_type = 'openstack'

    @functools.cached_property
    def identity(self) -> ks_client.Client:
        return ks_client.Client(
            session=get_session_for_resource(self.resource)
        )

    def create_project(self, project_name) -> str:
        openstack_project = self.identity.projects.create(
            name=project_name,
            domain=self.resource.get_attribute(attributes.RESOURCE_PROJECT_DOMAIN),
            enabled=True,
        )
        return openstack_project.id

    def reactivate_project(self, project_id):
        openstack_project = self.identity.projects.get(project_id)
        openstack_project.update(enabled=True)

    def disable_project(self, project_id):
        self.identity.projects.update(project_id, enabled=False)

    def set_quota(self, project_id):
        session = get_session_for_resource(self.resource)
        # If an attribute with the appropriate name is associated with an
        # allocation, set that as the quota. Otherwise, multiply
        # the quantity attribute via the mapping table above.
        for service_name, service in QUOTA_KEY_MAPPING.items():
            # No need to do any calculations here, just go through each service
            # and set the value in the attribute.
            payload = dict()
            for coldfront_attr, openstack_key in service['keys'].items():
                if value := self.allocation.get_attribute(coldfront_attr):
                    payload[openstack_key] = value

            if service_name == 'network':
                client = neutronclient.Client(session=session)
                client.update_quota(project_id, body={'quota': payload})
            elif service_name == 'volume':
                client = cinderclient.Client(session=session, version=3)
                client.quotas.update(project_id, **payload)
            elif service_name == 'compute':
                client = novaclient.Client(session=session, version=2)
                client.quotas.update(project_id, **payload)
            elif service_name == 'object':
                try:
                    # If you want to perform operation on a project different
                    # from the one you authenticated as, you must specify the
                    # endpoint manually. Endpoint url is in the form:
                    # "http://172.16.109.217:8085/v1/AUTH_$(project_id)s"
                    # or tenant_id instead of project_id.
                    swift_service = self.identity.services.find(name='swift')
                    url = self.identity.endpoints.list(service=swift_service,
                                                       interface='public')[0].url
                    url = url.replace('$(project_id)s', project_id)
                    url = url.replace('$(tenant_id)s', project_id)

                    client = swiftclient.Connection(session=session,
                                                    preauthurl=url)
                    # Note(knikolla): For consistency with other OpenStack quotas
                    # we're storing this as GB on the attribute and then
                    # converting to bytes for Swift.
                    # 1 GB = 1 000 000 000 B = 10^9 B
                    payload['X-Account-Meta-Quota-Bytes'] *= 1000000000
                    client.post_account(headers=payload)
                except ksa_exceptions.NotFound:
                    logger.debug('No swift available, skipping its quota.')

    def get_user_payload_for_resource(self, username):
        domain_id = self.resource.get_attribute(attributes.RESOURCE_USER_DOMAIN)
        idp_id = self.resource.get_attribute(attributes.RESOURCE_IDP)
        protocol = self.resource.get_attribute(attributes.RESOURCE_FEDERATION_PROTOCOL) or 'openid'
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

    def get_federated_user(self, username):
        # Query by unique_id
        query_response = get_session_for_resource(self.resource).get(
            f'{self.resource.get_attribute(attributes.RESOURCE_AUTH_URL)}/v3/users?unique_id={username}'
        ).json()
        if query_response['users']:
            return query_response['users'][0]

        # Query by name as a fallback (this might return a non-federated user)
        query_response = get_session_for_resource(self.resource).get(
            f'{self.resource.get_attribute(attributes.RESOURCE_AUTH_URL)}/v3/users?'
            f'name={username}&domain_id={self.resource.get_attribute(attributes.RESOURCE_USER_DOMAIN)}'
        ).json()
        if query_response['users']:
            return query_response['users'][0]

    def create_federated_user(self, unique_id):
        create_response = get_session_for_resource(self.resource).post(
            f'{self.resource.get_attribute(attributes.RESOURCE_AUTH_URL)}/v3/users',
            json=self.get_user_payload_for_resource(unique_id)
        )
        if create_response.ok:
            return create_response.json()['user']

    def assign_role_on_user(self, username, project_id):
        role = self.identity.roles.find(name=self.member_role_name)

        user = self.get_federated_user(username)
        self.identity.roles.grant(user=user['id'],
                                  project=project_id,
                                  role=role)

    def remove_role_from_user(self, username, project_id):
        role = self.identity.roles.find(name=self.member_role_name)

        if user := self.get_federated_user(username):
            self.identity.roles.revoke(user=user['id'], project=project_id, role=role)

    def create_default_network(self, project_id):
        neutron = neutronclient.Client(session=get_session_for_resource(self.resource))

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
                    'cidr': self.resource.get_attribute(
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
                        "network_id": self.resource.get_attribute(
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

    def create_project_defaults(self, project_id):
        if self.resource.get_attribute(attributes.RESOURCE_DEFAULT_PUBLIC_NETWORK):
            logger.info(f'Creating default network for project '
                        f'{project_id}.')
            self.create_default_network(
                self.allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
            )
        else:
            logger.info(f'No public network configured. Skipping default '
                        f'network creation for project {project_id}.')
