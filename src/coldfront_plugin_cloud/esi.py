import logging
import functools
import os

from keystoneauth1.identity import v3
from keystoneauth1 import session

from coldfront_plugin_cloud import attributes, utils
from coldfront_plugin_cloud.openstack import OpenStackResourceAllocator

class ESIResourceAllocator(OpenStackResourceAllocator):

    QUOTA_KEY_MAPPING = {
        'network': {
            'keys': {
                attributes.ESI_FLOATING_IPS: 'floatingip',
                attributes.ESI_NETWORKS: 'network'
            }
        }
    }

    QUOTA_KEY_MAPPING_ALL_KEYS = {quota_key: quota_name for k in QUOTA_KEY_MAPPING.values() for quota_key, quota_name in k['keys'].items()}

    resource_type = 'esi'

    def get_quota(self, project_id):
        quotas = dict()

        network_quota = self.network.show_quota(project_id)['quota']
        for k in self.QUOTA_KEY_MAPPING['network']['keys'].values():
            quotas[k] = network_quota.get(k)

        return quotas
