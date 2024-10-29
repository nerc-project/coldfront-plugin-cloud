from unittest import mock

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud.openshift import OpenShiftResourceAllocator


class TestOpenshiftUser(base.TestBase):
    def setUp(self) -> None:
        mock_resource = mock.Mock()
        mock_allocation = mock.Mock()
        self.mock_openshift_allocator = OpenShiftResourceAllocator(mock_resource, mock_allocation)
        self.mock_openshift_allocator.id_provider = "fake_idp"
        self.mock_openshift_allocator.logger = mock.Mock()
        self.mock_openshift_allocator.k8_client = mock.Mock()

    def test_get_federated_user(self):
        fake_user = mock.Mock(spec=["to_dict"])
        fake_user.to_dict.return_value = {"identities": ["fake_idp:fake_user"]}
        self.mock_openshift_allocator.k8_client.resources.get.return_value.get.return_value = fake_user

        output = self.mock_openshift_allocator.get_federated_user("fake_user")
        self.assertEqual(output, {"username": "fake_user"})

    def test_get_federated_user(self):
        fake_user = mock.Mock(spec=["to_dict"])
        fake_user.to_dict.return_value = {"identities": ["fake_idp:fake_user"]}
        self.mock_openshift_allocator.k8_client.resources.get.return_value.get.return_value = fake_user

        output = self.mock_openshift_allocator.get_federated_user("fake_user_2")
        self.assertEqual(output, None)
        self.mock_openshift_allocator.logger.info.assert_called_with("404: user (fake_user_2) does not exist")
