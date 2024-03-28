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

from coldfront_plugin_cloud.openstack import OpenStackResourceAllocator

# (Quan Pham) TODO Know which resources ESI needs, and their multipliers
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

    # (Quan Pham) TODO implement setting quotas for ESI resource
    # And know which functions needs to be implement specially for ESI
    def set_quota(self, project_id):
        pass

    def get_quota(self, project_id):
        pass

    def create_default_network(self, project_id):
        pass
