from unittest import mock

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud.openshift import OpenShiftResourceAllocator


class TestOpenshiftQuota(base.TestBase):
    def setUp(self) -> None:
        mock_resource = mock.Mock()
        mock_allocation = mock.Mock()
        self.allocator = OpenShiftResourceAllocator(mock_resource, mock_allocation)
        self.allocator.id_provider = "fake_idp"
        self.allocator.k8_client = mock.Mock()

    @mock.patch("coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._openshift_get_project", mock.Mock())
    def test_get_resourcequotas(self):
        fake_quota = mock.Mock(spec=["to_dict"])
        fake_quota.to_dict.return_value = {"items": []}
        self.allocator.k8_client.resources.get.return_value.get.return_value = fake_quota
        res = self.allocator._openshift_get_resourcequotas("fake-project")
        self.allocator.k8_client.resources.get.return_value.get.assert_called()
        assert res == []


    def test_delete_quota(self):
        fake_quota = mock.Mock(spec=["to_dict"])
        fake_quota.to_dict.return_value = {}
        self.allocator.k8_client.resources.get.return_value.delete.return_value = fake_quota
        res = self.allocator._openshift_delete_resourcequota("test-project", "test-quota")
        self.allocator.k8_client.resources.get.return_value.delete.assert_called()
        assert res == {}


    @mock.patch("coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._openshift_get_resourcequotas")
    def test_delete_moc_quota(self, fake_get_resourcequotas):
        fake_get_resourcequotas.return_value = [{"metadata": {"name": "fake-quota"}}]
        self.allocator.delete_moc_quotas("test-project")
        self.allocator.k8_client.resources.get.return_value.delete.assert_any_call(
            namespace="test-project", name="fake-quota"
        )


    @mock.patch("coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._wait_for_quota_to_settle")
    def test_create_shift_quotas(self, fake_wait_quota):
        quotadefs = {
            "metadata": {"name": "fake-project-project"},
            "spec": {"hard": {"configmaps": "1", "cpu": "1", "resourcequotas": "1"}},
        }

        self.allocator.k8_client.resources.get.return_value.create.return_value = mock.Mock()

        self.allocator._openshift_create_resourcequota("fake-project", quotadefs)

        self.allocator.k8_client.resources.get.return_value.create.assert_called_with(
            namespace="fake-project",
            body={
                "metadata": {"name": "fake-project-project"},
                "spec": {"hard": {"configmaps": "1", "cpu": "1", "resourcequotas": "1"}},
            },
        )

        fake_wait_quota.assert_called()


    def test_wait_for_quota_to_settle(self):
        fake_quota = mock.Mock(spec=["to_dict"])
        fake_quota.to_dict.return_value = {
            "metadata": {"name": "fake-quota"},
            "spec": {"hard": {"resourcequotas": "1"}},
            "status": {"used": {"resourcequotas": "1"}},
        }
        self.allocator.k8_client.resources.get.return_value.get.return_value = fake_quota

        self.allocator._wait_for_quota_to_settle("fake-project", fake_quota.to_dict())

        self.allocator.k8_client.resources.get.return_value.get.assert_called_with(
            namespace="fake-project",
            name="fake-quota",
        )

    @mock.patch("coldfront_plugin_cloud.openshift.OpenShiftResourceAllocator._get_moc_quota_from_resourcequotas")
    def test_get_moc_quota(self, fake_get_quota):
        fake_get_quota.return_value = {
            ":services": {"value": "2"},
            ":configmaps": {"value": None},
            ":cpu": {"value": "1000"},
        }
        res = self.allocator.get_quota("fake-project")
        assert res == {
            "Version": "0.9",
            "Kind": "MocQuota",
            "ProjectName": "fake-project",
            "Quota": {
                ":services": {"value": "2"},
                ":configmaps": {"value": None},
                ":cpu": {"value": "1000"},
            },
        }


    
