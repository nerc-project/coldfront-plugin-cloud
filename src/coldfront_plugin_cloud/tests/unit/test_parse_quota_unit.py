from django.core.management.base import CommandError

from coldfront_plugin_cloud.management.commands.validate_allocations import Command
from coldfront_plugin_cloud.tests import base


class TestParseQuotaUnit(base.TestBase):
    def test_parse_quota_unit(self):
        parse_quota_unit = Command().parse_quota_value
        answer_dict = [
            (("5m", "cpu"), 5 * 10**-3),
            (("10", "cpu"), 10),
            (("10k", "cpu"), 10 * 10**3),
            (("55M", "cpu"), 55 * 10**6),
            (("2G", "cpu"), 2 * 10**9),
            (("3T", "cpu"), 3 * 10**12),
            (("4P", "cpu"), 4 * 10**15),
            (("5E", "cpu"), 5 * 10**18),
            (("10", "memory"), 10),
            (("125Ki", "memory"), 125 * 2**10),
            (("55Mi", "memory"), 55 * 2**20),
            (("2Gi", "memory"), 2 * 2**30),
            (("3Ti", "memory"), 3 * 2**40),
        ]
        for (input_value, resource_type), expected in answer_dict:
            self.assertEqual(parse_quota_unit(input_value, resource_type), expected)

        with self.assertRaises(CommandError):
            parse_quota_unit("abc", "foo")  # Non-numeric input
