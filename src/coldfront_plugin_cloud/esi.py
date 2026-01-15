from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud.openstack import OpenStackResourceAllocator


class ESIResourceAllocator(OpenStackResourceAllocator):
    SERVICE_QUOTA_MAPPING = {
        "network": [attributes.QUOTA_FLOATING_IPS, attributes.QUOTA_NETWORKS],
    }
    resource_type = "esi"

    def get_quota(self, project_id):
        quotas = dict()
        quotas = self._get_network_quota(quotas, project_id)
        return quotas
