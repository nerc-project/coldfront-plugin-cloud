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
