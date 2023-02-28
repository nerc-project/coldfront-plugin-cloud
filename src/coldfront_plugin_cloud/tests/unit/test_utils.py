import re
from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud import utils

class TestGetSanitizedProjectName(base.TestBase):
    def test_project_name(self):
        # Ensure that the sanitized project name conforms to DNS 1123 spec (besides the max length)
        project_name = "---TEST - Software & Application Innovation Lab (SAIL) - TEST Projects   "
        sanitized_name = utils.get_sanitized_project_name(project_name)
        self.assertTrue(re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", sanitized_name))
