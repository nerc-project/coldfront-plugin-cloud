from unittest import mock

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud.openshift import OpenShiftResourceAllocator


class TestOpenshiftResourceAllocator(OpenShiftResourceAllocator):
    def __init__(self):
        self.resource = mock.Mock()
        self.allocation = mock.Mock()
        self.resource_quotaspecs = mock.Mock()
        self.id_provider = "fake_idp"
        self.k8_client = mock.Mock()

        self.verify = False
        self.safe_resource_name = "foo"
        self.apis = {}
        self.member_role_name = "admin"


class TestUnitOpenshiftBase(base.TestBase):
    def setUp(self) -> None:
        self.allocator = TestOpenshiftResourceAllocator()
