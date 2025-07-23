from unittest import mock

import kubernetes.dynamic.exceptions as kexc

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud.openshift import OpenShiftResourceAllocator


class TestMocOpenShiftRBAC(base.TestBase):
    def setUp(self) -> None:
        mock_resource = mock.Mock()
        mock_allocation = mock.Mock()
        self.allocator = OpenShiftResourceAllocator(mock_resource, mock_allocation)
        self.allocator.id_provider = "fake_idp"
        self.allocator.k8_client = mock.Mock()
        self.allocator.member_role_name = "admin"

    def test_user_in_rolebindings_false(self):
        fake_rb = {
            "subjects": [
                {
                    "kind": "User",
                    "name": "fake-user-2",
                }
            ]
        }
        output = self.allocator._user_in_rolebinding("fake-user", fake_rb)
        self.assertFalse(output)

    def test_user_in_rolebindings_true(self):
        fake_rb = {
            "subjects": [
                {
                    "kind": "User",
                    "name": "fake-user",
                }
            ]
        }
        output = self.allocator._user_in_rolebinding("fake-user", fake_rb)
        self.assertTrue(output)

    @mock.patch(
        "coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._openshift_get_rolebindings"
    )
    @mock.patch(
        "coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._openshift_update_rolebindings"
    )
    def test_add_user_to_role(self, fake_update_rb, fake_get_rb):
        fake_get_rb.return_value = {
            "subjects": [],
        }
        self.allocator.assign_role_on_user("fake-user", "fake-project")
        fake_update_rb.assert_called_with(
            "fake-project", {"subjects": [{"kind": "User", "name": "fake-user"}]}
        )

    @mock.patch(
        "coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._openshift_get_rolebindings"
    )
    @mock.patch(
        "coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._openshift_create_rolebindings"
    )
    def test_add_user_to_role_not_exists(self, fake_create_rb, fake_get_rb):
        fake_error = kexc.NotFoundError(mock.Mock())
        fake_get_rb.side_effect = fake_error
        self.allocator.assign_role_on_user("fake-user", "fake-project")
        fake_create_rb.assert_called_with("fake-project", "fake-user", "admin")

    @mock.patch(
        "coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._openshift_get_rolebindings"
    )
    def test_remove_user_from_role(self, fake_get_rb):
        fake_get_rb.return_value = {
            "subjects": [{"kind": "User", "name": "fake-user"}],
        }
        self.allocator.k8_client.resources.get.return_value.patch.return_value.to_dict.return_value = {}
        self.allocator.remove_role_from_user("fake-user", "fake-project")
        self.allocator.k8_client.resources.get.return_value.patch.assert_called_with(
            body={"subjects": []}, namespace="fake-project"
        )

    def test_remove_user_from_role_not_exists(self):
        fake_error = kexc.NotFoundError(mock.Mock())
        self.allocator.k8_client.resources.get.return_value.get.side_effect = fake_error
        self.allocator.remove_role_from_user("fake-project", "fake-user")
        self.allocator.k8_client.resources.get.return_value.patch.assert_not_called()

    def test_get_rolebindings(self):
        fake_rb = mock.Mock(spec=["to_dict"])
        fake_rb.to_dict.return_value = {"subjects": []}
        self.allocator.k8_client.resources.get.return_value.get.return_value = fake_rb
        res = self.allocator._openshift_get_rolebindings("fake-project", "admin")
        self.assertEqual(res, fake_rb.to_dict())

    def test_get_rolebindings_no_subjects(self):
        fake_rb = mock.Mock(spec=["to_dict"])
        fake_rb.to_dict.return_value = {}
        self.allocator.k8_client.resources.get.return_value.get.return_value = fake_rb
        res = self.allocator._openshift_get_rolebindings("fake-project", "admin")
        self.assertEqual(res, {"subjects": []})

    def test_list_rolebindings(self):
        fake_rb = mock.Mock(spec=["to_dict"])
        fake_rb.to_dict.return_value = {
            "items": ["rb1", "rb2"],
        }
        self.allocator.k8_client.resources.get.return_value.get.return_value = fake_rb
        res = self.allocator._openshift_list_rolebindings("fake-project")
        self.assertEqual(res, ["rb1", "rb2"])

    def test_list_rolebindings_not_exists(self):
        fake_error = kexc.NotFoundError(mock.Mock())
        self.allocator.k8_client.resources.get.return_value.get.side_effect = fake_error
        res = self.allocator._openshift_list_rolebindings("fake-project")
        self.assertEqual(res, [])

    def test_create_rolebindings(self):
        fake_rb = mock.Mock(spec=["to_dict"])
        fake_rb.to_dict.return_value = {}
        self.allocator.k8_client.resources.get.return_value.create.return_value = (
            fake_rb
        )
        res = self.allocator._openshift_create_rolebindings(
            "fake-project", "fake-user", "admin"
        )
        self.assertEqual(res, {})
        self.allocator.k8_client.resources.get.return_value.create.assert_called_with(
            namespace="fake-project",
            body={
                "metadata": {"name": "admin", "namespace": "fake-project"},
                "subjects": [{"name": "fake-user", "kind": "User"}],
                "roleRef": {"name": "admin", "kind": "ClusterRole"},
            },
        )
