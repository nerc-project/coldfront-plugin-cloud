import copy

from coldfront_plugin_cloud import openshift
from coldfront_plugin_cloud.tests import base


class TestOpenShiftUtils(base.TestBase):
    def test_parse_quota_unit(self):
        parse_quota_unit = openshift.parse_quota_value
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

        with self.assertRaises(ValueError):
            parse_quota_unit("abc", "foo")  # Non-numeric input

    def test_limit_ranges_diff(self):
        # identical limit ranges, different units for memory -> no differences
        expected = openshift.LIMITRANGE_DEFAULTS
        actual = [copy.deepcopy(expected[0])]
        actual[0]["default"]["memory"] = "4Gi"
        diffs = openshift.limit_ranges_diff(expected, actual)
        self.assertEqual(diffs, [])

        # type mismatch
        actual[0]["type"] = "Pod"
        actual[0]["default"]["cpu"] = "2"
        del actual[0]["min"]["memory"]
        diffs = openshift.limit_ranges_diff(expected, actual)
        self.assertTrue(
            openshift.LimitRangeDifference("type", "Container", "Pod") in diffs
        )

        # Contains extra fields, [default][cpu] value mismatch (1 vs 2), and missing [min][memory]
        actual = [copy.deepcopy(expected[0])]
        actual[0]["foo"] = "bar"
        actual[0]["default"]["ephemeral-storage"] = "10Gi"
        actual[0]["default"]["cpu"] = "2"
        del actual[0]["min"]["memory"]
        diffs = openshift.limit_ranges_diff(expected, actual)
        self.assertTrue(
            openshift.LimitRangeDifference(
                "default,ephemeral-storage", None, 10 * 2**30
            )
            in diffs
        )
        self.assertTrue(openshift.LimitRangeDifference("foo", None, "bar") in diffs)
        self.assertTrue(openshift.LimitRangeDifference("default,cpu", 1, 2) in diffs)
        self.assertTrue(
            openshift.LimitRangeDifference("min,memory", 32 * 2**20, None) in diffs
        )
