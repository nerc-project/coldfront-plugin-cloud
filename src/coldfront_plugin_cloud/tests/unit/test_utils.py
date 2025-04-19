import re
import secrets
from random import randrange

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud import utils

class TestGetSanitizedProjectName(base.TestBase):
    def test_project_name(self):
        # Ensure that the sanitized project name conforms to DNS 1123 spec (besides the max length)
        project_name = "---TEST - Software & Application Innovation Lab (SAIL) - TEST Projects   "
        sanitized_name = utils.get_sanitized_project_name(project_name)
        self.assertTrue(re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", sanitized_name))

    def test_get_unique_project_name_length(self):
        project_name = secrets.token_hex(100)
        max_length = randrange(50, 60)

        self.assertGreater(len(project_name), max_length)
        new_name = utils.get_unique_project_name(project_name, max_length=max_length)
        self.assertEqual(len(new_name), max_length)


class TestCheckIfQuotaAttr(base.TestCase):
    def test_valid_quota_attr(self):
        self.assertTrue(utils.check_if_quota_attr("OpenShift Limit on CPU Quota"))

    def test_invalid_quota_attr(self):
        self.assertFalse(utils.check_if_quota_attr("Test"))
        self.assertFalse(utils.check_if_quota_attr("Allocated Project ID"))


class TestColdfrontToOpenshiftQuotaName(base.TestCase):
    def test_valid_mapping(self):
        result = utils.coldfront_to_openshift_quota_name("OpenShift Limit on CPU Quota")
        self.assertEqual(result, "limits.cpu")

    def test_missing_mapping(self):
        with self.assertRaises(TypeError):
            utils.coldfront_to_openshift_quota_name("Unknown Quota")


class TestGetNewCloudQuota(base.TestCase):
    def test_get_requested_quota(self):
        data = [
            {"name": "OpenShift Limit on CPU Quota", "new_value": "2"},
            {"name": "OpenShift Limit on RAM Quota (MiB)", "new_value": ""}
        ]

        result = utils.get_new_cloud_quota(data)
        self.assertEqual(result, {"OpenShift Limit on CPU Quota": "2"})


class TestCheckChangeRequests(base.TestBase):
    def test_check_usage(self):
        # No error case, usage is lower
        test_quota_usage = {
            "limits.cpu": "1",
            "limits.memory": "2Gi",
            "limits.ephemeral-storage": "10Gi",    # Other quotas should be ignored
            "requests.storage": "40Gi",
            "requests.nvidia.com/gpu": "0",
            "persistentvolumeclaims": "4",
        }
        test_requested_quota = {
            "OpenShift Limit on CPU Quota": "2"
        }

        self.assertEqual([], utils.check_cloud_usage_is_lower(test_requested_quota, test_quota_usage))

        # Requested cpu (2) lower than current used, should return errors
        test_quota_usage["limits.cpu"] = "16"
        self.assertEqual(
            [
                (
                    "Current quota usage for OpenShift Limit on CPU Quota "
                    "(16) is higher than "
                    "the requested amount (2)."
                )
            ],
            utils.check_cloud_usage_is_lower(test_requested_quota, test_quota_usage)
        )
