from unittest import mock

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud.openshift import OpenShiftResourceAllocator


class TestUnitOpenshiftBase(base.TestBase):
    def setUp(self) -> None:
        mock_resource = mock.Mock()
        mock_allocation = mock.Mock()
        self.allocator = OpenShiftResourceAllocator(mock_resource, mock_allocation)
        self.allocator.id_provider = "fake_idp"
        self.allocator.k8_client = mock.Mock()
