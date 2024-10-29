from unittest import mock

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud.openshift import OpenShiftResourceAllocator


class TestOpenshiftUser(base.TestBase):
    def setUp(self) -> None:
        mock_resource = mock.Mock()
        mock_allocation = mock.Mock()
        self.allocator = OpenShiftResourceAllocator(mock_resource, mock_allocation)
        self.allocator.id_provider = "fake_idp"
        self.allocator.k8_client = mock.Mock()

    def test_get_federated_user(self):
        fake_user = mock.Mock(spec=["to_dict"])
        fake_user.to_dict.return_value = {"identities": ["fake_idp:fake_user"]}
        self.allocator.k8_client.resources.get.return_value.get.return_value = fake_user

        output = self.allocator.get_federated_user("fake_user")
        self.assertEqual(output, {"username": "fake_user"})

    def test_get_federated_user_not_exist(self):
        fake_user = mock.Mock(spec=["to_dict"])
        fake_user.to_dict.return_value = {"identities": ["fake_idp:fake_user"]}
        self.allocator.k8_client.resources.get.return_value.get.return_value = fake_user

        output = self.allocator.get_federated_user("fake_user_2")
        self.assertEqual(output, None)
