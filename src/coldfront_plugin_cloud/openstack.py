import hashlib
import functools
import logging
import os
import urllib.parse

import swiftclient
from swiftclient import exceptions as swift_exceptions
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneauth1 import exceptions as ksa_exceptions
from keystoneclient.v3 import client as ks_client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient

from coldfront_plugin_cloud import attributes, base, utils

logger = logging.getLogger(__name__)

# 1 GB = 1 000 000 000 B = 10^9 B
GB_IN_BYTES = 1000000000

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
            attributes.QUOTA_OBJECT_GB: 'x-account-meta-quota-bytes',
        }
    },
    'volume': {
        'keys': {
            attributes.QUOTA_VOLUMES: 'volumes',
            attributes.QUOTA_VOLUMES_GB: 'gigabytes',
        }
    },
}

COLDFRONT_RGW_SWIFT_INIT_USER = 'coldfront-swift-init'

QUOTA_KEY_MAPPING_ALL_KEYS = dict()
for service in QUOTA_KEY_MAPPING.keys():
    QUOTA_KEY_MAPPING_ALL_KEYS.update(QUOTA_KEY_MAPPING[service]['keys'])

def get_session_for_resource_via_password(resource, username, password, project_id):
    auth_url = resource.get_attribute(attributes.RESOURCE_AUTH_URL)
    user_domain = resource.get_attribute(attributes.RESOURCE_USER_DOMAIN)
    auth = v3.Password(auth_url=auth_url,
        username=username,
        password=password,
        project_id=project_id,
        user_domain_name=user_domain,
    )
    sesh = session.Session(
        auth,
        verify=os.environ.get('FUNCTIONAL_TESTS', '') != 'True'
    )
    return sesh

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

    project_name_max_length = 64

    @functools.cached_property
    def session(self) -> session.Session:
        return get_session_for_resource(self.resource)

    @functools.cached_property
    def identity(self) -> ks_client.Client:
        return ks_client.Client(session=self.session)

    @functools.cached_property
    def compute(self) -> novaclient.Client:
        return novaclient.Client(session=self.session, version=2)

    @functools.cached_property
    def volume(self):
        return cinderclient.Client(session=self.session, version=3)

    @functools.cached_property
    def network(self):
        return neutronclient.Client(session=self.session)

    @functools.lru_cache()
    def object(self, project_id=None, session=None) -> swiftclient.Connection:
        preauth_url = None
        session = session or self.session
        if project_id:
            swift_endpoint = session.get_endpoint(
                service_type='object-store',
                interface='public',
            )
            preauth_url = swift_endpoint.replace(
                session.get_project_id(),
                project_id,
            )
        logger.debug(f'creating swift client: preauthurl={preauth_url}')
        return swiftclient.Connection(
            session=session,
            preauthurl=preauth_url,
        )

    def create_project(self, suggested_project_name) -> base.ResourceAllocator.Project:
        project_name = utils.get_unique_project_name(
            suggested_project_name,
            max_length=self.project_name_max_length)

        openstack_project = self.identity.projects.create(
            name=project_name,
            domain=self.resource.get_attribute(attributes.RESOURCE_PROJECT_DOMAIN),
            enabled=True,
        )
        return self.Project(project_name, openstack_project.id)

    def reactivate_project(self, project_id):
        openstack_project = self.identity.projects.get(project_id)
        openstack_project.update(enabled=True)

    def disable_project(self, project_id):
        self.identity.projects.update(project_id, enabled=False)

    def set_quota(self, project_id):
        # If an attribute with the appropriate name is associated with an
        # allocation, set that as the quota. Otherwise, multiply
        # the quantity attribute via the mapping table above.
        for service_name, service in QUOTA_KEY_MAPPING.items():
            # No need to do any calculations here, just go through each service
            # and set the value in the attribute.
            payload = dict()
            for coldfront_attr, openstack_key in service['keys'].items():
                value = self.allocation.get_attribute(coldfront_attr)
                if value is not None:
                    payload[openstack_key] = value

            if not payload:
                # Skip if service doesn't have any associated attributes
                continue

            if service_name == 'network':
                self.network.update_quota(project_id, body={'quota': payload})
            elif service_name == 'volume':
                self.volume.quotas.update(project_id, **payload)
            elif service_name == 'compute':
                self.compute.quotas.update(project_id, **payload)
            elif service_name == 'object':
                self._set_object_quota(project_id, payload)

    def _set_object_quota(self, project_id, payload):
        try:
            # Note(knikolla): For consistency with other OpenStack
            # quotas we're storing this as GB on the attribute and
            # converting to bytes for Swift.
            payload[QUOTA_KEY_MAPPING['object']['keys'][
                attributes.QUOTA_OBJECT_GB]
            ] *= GB_IN_BYTES
            self.object(project_id).post_account(headers=payload)
        except ksa_exceptions.catalog.EndpointNotFound:
            logger.debug('No swift available, skipping its quota.')
        except swiftclient.exceptions.ClientException as e:
            if e.http_status == 403:
                self._init_rgw_for_project(project_id)
                self.object(project_id).post_account(headers=payload)
            else:
                raise

    def _init_rgw_for_project(self, project_id):
        var_name = utils.env_safe_name(self.resource.name)
        phash = hashlib.sha512(
            os.environ.get(
                f'OPENSTACK_{var_name}_APPLICATION_CREDENTIAL_SECRET'
            ).encode('utf-8')
        )

        password = phash.hexdigest()[0:int(phash.block_size/2)]

        try:
            user = self.identity.users.create(
                name=COLDFRONT_RGW_SWIFT_INIT_USER,
                password=password,
            )
        except ksa_exceptions.http.Conflict:
            logger.debug(f'rgw swift init user already exists: {COLDFRONT_RGW_SWIFT_INIT_USER}')

        self.assign_role_on_user(COLDFRONT_RGW_SWIFT_INIT_USER, project_id)

        usesh = get_session_for_resource_via_password(
            resource=self.resource,
            username=COLDFRONT_RGW_SWIFT_INIT_USER,
            password=password,
            project_id=project_id,
        )
        sw = self.object(session=usesh, project_id=project_id)
        stat = sw.head_account()
        logger.debug(f'rgw swift stat for {project_id}:\n{stat}')
        self.remove_role_from_user(COLDFRONT_RGW_SWIFT_INIT_USER, project_id)

    def get_quota(self, project_id):
        quotas = dict()

        compute_quota = self.compute.quotas.get(project_id)
        for k in QUOTA_KEY_MAPPING['compute']['keys'].values():
            quotas[k] = compute_quota.__getattr__(k)

        volume_quota = self.volume.quotas.get(project_id)
        for k in QUOTA_KEY_MAPPING['volume']['keys'].values():
            quotas[k] = volume_quota.__getattr__(k)

        network_quota = self.network.show_quota(project_id)['quota']
        for k in QUOTA_KEY_MAPPING['network']['keys'].values():
            quotas[k] = network_quota.get(k)

        key = QUOTA_KEY_MAPPING['object']['keys'][attributes.QUOTA_OBJECT_GB]
        try:
            swift = self.object(project_id).head_account()
            quotas[key] = int(int(swift.get(key)) / GB_IN_BYTES)
        except ksa_exceptions.catalog.EndpointNotFound:
            logger.debug('No swift available, skipping its quota.')
        except swiftclient.exceptions.ClientException as e:
            if e.http_status == 403:
                self._init_rgw_for_project(project_id)
                swift = self.object(project_id).head_account()
                quotas[key] = int(int(swift.get(key)) / GB_IN_BYTES)
            else:
                raise
        except (ValueError, TypeError):
            logger.info('No swift quota set.')

        return quotas

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
        try:
            create_response = get_session_for_resource(self.resource).post(
                f'{self.resource.get_attribute(attributes.RESOURCE_AUTH_URL)}/v3/users',
                json=self.get_user_payload_for_resource(unique_id)
            )
            return create_response.json()['user']
        except ksa_exceptions.Conflict:
            return self.get_federated_user(unique_id)

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
            print(f'Default network with ID {network["network"]["id"]} '
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
            print(f'Default network with ID {network["network"]["id"]} '
                        f'created for project {project_id}.')

        # Get or create default subnet
        subnets = neutron.list_subnets(project_id=project_id,
                                       name='default_subnet')
        if subnets := subnets['subnets']:
            subnet = subnets[0]
            print(f'Default subnet with ID {subnet["subnet"]["id"]} '
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
            print(f'Default subnet with ID {subnet["subnet"]["id"]} '
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
            print(f'Router {router_id} already connected to network {network_id} for '
                        f'project {project_id}.')
        else:
            default_interface_payload = {'subnet_id': subnet_id}
            neutron.add_interface_router(router_id,
                                         body=default_interface_payload)
            print(f'Router {router_id} connected to subnet {subnet_id} for '
                        f'project {project_id}.')
            
        ports = neutron.list_ports(project_id=project_id,
                                   device_id=router_id,
                                   network_id=network_id)['ports']
        while ports[0]['status']:
            print("polling port")
            ports = neutron.list_ports(project_id=project_id,
                                   device_id=router_id,
                                   network_id=network_id)['ports']

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

    def get_users(self, project_id):
        """ Return users with a role in a project"""
        role_name = self.resource.get_attribute(attributes.RESOURCE_ROLE)
        role = self.identity.roles.find(name=role_name)
        role_assignments = self.identity.role_assignments.list(role=role.id,
                                                               project=project_id,
                                                               include_names=True)
        user_names = set(role_assignment.user["name"] for role_assignment in role_assignments)
        return user_names
