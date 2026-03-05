from coldfront_plugin_cloud.openstack import OpenStackResourceAllocator


class ESIResourceAllocator(OpenStackResourceAllocator):
    resource_type = "esi"

    def get_quota(self, project_id):
        quotas = dict()
        quotas = self._get_network_quota(quotas, project_id)
        return quotas
