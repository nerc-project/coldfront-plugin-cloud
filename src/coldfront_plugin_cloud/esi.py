import logging
import functools
import os

from keystoneauth1.identity import v3
from keystoneauth1 import session


from coldfront_plugin_cloud import attributes, utils

from coldfront_plugin_cloud.openstack import OpenStackResourceAllocator

logger = logging.getLogger(__name__)

QUOTA_KEY_MAPPING = {
    'network': {
        'keys': {
            attributes.ESI_FLOATING_IPS: 'floatingip',
            attributes.ESI_NETWORKS: 'network'
        }
    },
}

def get_session_for_resource(resource):
    auth_url = resource.get_attribute(attributes.RESOURCE_AUTH_URL)
    var_name = utils.env_safe_name(resource.name)
    auth = v3.ApplicationCredential(
        auth_url=auth_url,
        application_credential_id=os.environ.get(
            f'ESI_{var_name}_APPLICATION_CREDENTIAL_ID'),
        application_credential_secret=os.environ.get(
            f'ESI_{var_name}_APPLICATION_CREDENTIAL_SECRET')
    )
    return session.Session(
        auth,
        verify=os.environ.get('FUNCTIONAL_TESTS', '') != 'True'
    )


class ESIResourceAllocator(OpenStackResourceAllocator):

    resource_type = 'esi'

    @functools.cached_property
    def session(self) -> session.Session:
        return get_session_for_resource(self.resource)

    def set_quota(self, project_id):
        for service_name, service in QUOTA_KEY_MAPPING.items():
            if service_name not in self.available_service_types:
                logger.error(f"Service {service_name} needed for ESI allocation not available!")
            else:
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


    def get_quota(self, project_id):
        quotas = dict()

        network_quota = self.network.show_quota(project_id)['quota']
        for k in QUOTA_KEY_MAPPING['network']['keys'].values():
            quotas[k] = network_quota.get(k)
