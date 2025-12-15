from unittest import mock
import json

import kubernetes.dynamic.exceptions as kexc

from coldfront_plugin_cloud.tests.unit.openshift import base


class TestOpenshiftUser(base.TestUnitOpenshiftBase):
    def test_get_federated_user(self):
        fake_user = mock.Mock(spec=["to_dict"])
        fake_user.to_dict.return_value = {"identities": ["fake_idp:fake_user"]}
        self.allocator.k8_client.resources.get.return_value.get.return_value = fake_user

        output = self.allocator.get_federated_user("fake_user")
        self.assertEqual(output, {"username": "fake_user"})

    def test_get_federated_user_not_exist(self):
        fake_error = kexc.NotFoundError(mock.Mock())
        fake_error.body = json.dumps(
            {
                "reason": "NotFound",
                "details": {
                    "name": "fake_user_2",
                },
            }
        )
        self.allocator.k8_client.resources.get.return_value.get.side_effect = fake_error

        output = self.allocator.get_federated_user("fake_user_2")
        self.assertEqual(output, None)

    def test_create_federated_user(self):
        fake_client_output = mock.Mock(spec=["to_dict"])
        fake_client_output.to_dict.return_value = {}
        self.allocator.k8_client.resources.get.return_value.create.return_value = (
            fake_client_output
        )

        self.allocator.create_federated_user("fake_user_name")

        # Assert called to create user
        self.allocator.k8_client.resources.get.return_value.create.assert_any_call(
            body={"metadata": {"name": "fake_user_name"}, "fullName": "fake_user_name"}
        )

        # Assert called to add identity
        self.allocator.k8_client.resources.get.return_value.create.assert_any_call(
            body={
                "providerName": "fake_idp",
                "providerUserName": "fake_user_name",
            }
        )

        # Assert called to add identity mapping
        self.allocator.k8_client.resources.get.return_value.create.assert_any_call(
            body={
                "user": {"name": "fake_user_name"},
                "identity": {"name": "fake_idp:fake_user_name"},
            }
        )

    def test_delete_user(self):
        fake_client_output = mock.Mock(spec=["to_dict"])
        fake_client_output.to_dict.return_value = {}
        self.allocator.k8_client.resources.get.return_value.delete.return_value = (
            fake_client_output
        )

        self.allocator._delete_user("fake_user_name")
        self.allocator.k8_client.resources.get.return_value.delete.assert_any_call(
            name="fake_user_name"
        )
        self.allocator.k8_client.resources.get.return_value.delete.assert_any_call(
            name="fake_idp:fake_user_name"
        )
