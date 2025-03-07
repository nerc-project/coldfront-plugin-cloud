import re
import secrets
from random import randrange

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud import utils


class TestGetSanitizedProjectName(base.TestBase):
    def test_project_name(self):
        # Ensure that the sanitized project name conforms to DNS 1123 spec (besides the max length)
        project_name = (
            "---TEST - Software & Application Innovation Lab (SAIL) - TEST Projects   "
        )
        sanitized_name = utils.get_sanitized_project_name(project_name)
        self.assertTrue(re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", sanitized_name))

    def test_get_unique_project_name_length(self):
        project_name = secrets.token_hex(100)
        max_length = randrange(50, 60)

        self.assertGreater(len(project_name), max_length)
        new_name = utils.get_unique_project_name(project_name, max_length=max_length)
        self.assertEqual(len(new_name), max_length)

    def test_env_safe_name(self):
        self.assertEqual(utils.env_safe_name("My Env-Var"), "MY_ENV_VAR")
        self.assertEqual(utils.env_safe_name("foo@bar!baz"), "FOO_BAR_BAZ")
        self.assertEqual(utils.env_safe_name(42), "42")
        self.assertEqual(utils.env_safe_name(None), "NONE")
        self.assertEqual(utils.env_safe_name("hello"), "HELLO")


class TestCheckIfQuotaAttr(base.TestCase):
    def test_valid_quota_attr(self):
        self.assertTrue(utils.check_if_quota_attr("OpenShift Limit on CPU Quota"))

    def test_invalid_quota_attr(self):
        self.assertFalse(utils.check_if_quota_attr("Test"))
        self.assertFalse(utils.check_if_quota_attr("Allocated Project ID"))


class TestGetNewCloudQuota(base.TestCase):
    def test_get_requested_quota(self):
        data = [
            {"name": "OpenShift Limit on CPU Quota", "new_value": "2"},
            {"name": "OpenShift Limit on RAM Quota (MiB)", "new_value": ""},
        ]

        result = utils.get_new_cloud_quota(data)
        self.assertEqual(result, {"OpenShift Limit on CPU Quota": "2"})


class TestCheckChangeRequests(base.TestBase):
    def test_check_usage(self):
        # No error case, usage is lower
        test_quota_usage = {
            "OpenShift Limit on CPU Quota": 2.0,
            "OpenShift Limit on RAM Quota (MiB)": 2048,
            "OpenShift Limit on Ephemeral Storage Quota (GiB)": 10,  # Other quotas should be ignored
        }
        test_requested_quota = {"OpenShift Limit on CPU Quota": "2"}

        self.assertEqual(
            [], utils.check_cloud_usage_is_lower(test_requested_quota, test_quota_usage)
        )

        # Requested cpu (2) lower than current used, should return errors
        test_quota_usage["OpenShift Limit on CPU Quota"] = 16
        self.assertEqual(
            [
                (
                    "Current quota usage for OpenShift Limit on CPU Quota "
                    "(16) is higher than "
                    "the requested amount (2)."
                )
            ],
            utils.check_cloud_usage_is_lower(test_requested_quota, test_quota_usage),
        )
