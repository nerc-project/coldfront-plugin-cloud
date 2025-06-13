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
