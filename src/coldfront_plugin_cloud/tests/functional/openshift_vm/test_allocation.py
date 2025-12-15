import os
import unittest

from coldfront_plugin_cloud import attributes, openshift_vm, tasks
from coldfront_plugin_cloud.tests import base


@unittest.skipUnless(os.getenv("FUNCTIONAL_TESTS"), "Functional tests not enabled.")
class TestAllocation(base.TestBase):
    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_openshift_resource(
            name="Microshift",
            api_url=os.getenv("OS_API_URL"),
            for_virtualization=True,
        )

    def test_new_allocation(self):
        # TODO must wait until we know what the quota values for openshift_vm are
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)
        allocator = openshift_vm.OpenShiftVMResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        self.assertEqual(allocation.get_attribute(attributes.QUOTA_LIMITS_CPU), 2 * 1)
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_LIMITS_MEMORY), 2 * 4096
        )
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB),
            2 * 5,
        )
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_REQUESTS_NESE_STORAGE), 2 * 20
        )
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_REQUESTS_VM_GPU_A100_SXM4), 2 * 0
        )
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_REQUESTS_VM_GPU_V100), 2 * 0
        )
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_REQUESTS_VM_GPU_H100), 2 * 0
        )
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_PVC), 2 * 2)

        quota = allocator.get_quota(project_id)
        # The return value will update to the most relevant unit, so
        # 2000m cores becomes 2 and 8192Mi becomes 8Gi
        self.assertEqual(
            quota,
            {
                "limits.cpu": "2",
                "limits.memory": "8Gi",
                "limits.ephemeral-storage": "10Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "40Gi",
                "requests.nvidia.com/A100_SXM4_40GB": "0",
                "requests.nvidia.com/GV100GL_Tesla_V100": "0",
                "requests.nvidia.com/H100_SXM5_80GB": "0",
                "persistentvolumeclaims": "4",
            },
        )
