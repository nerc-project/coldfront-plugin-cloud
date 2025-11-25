from decimal import Decimal
from pydantic import ValidationError

from coldfront_plugin_cloud import usage_models
from coldfront_plugin_cloud.tests import base


class TestUsageModels(base.TestBase):
    def test_usage_info(self):
        # valid: values coerced to Decimal
        ui = usage_models.UsageInfo(
            root={"su-a": Decimal("1.5"), "su-b": 2, "su-c": "3.25"}
        )
        self.assertIsInstance(ui.root, dict)
        self.assertEqual(ui.root["su-a"], Decimal("1.5"))
        self.assertEqual(ui.root["su-b"], Decimal("2"))
        self.assertEqual(ui.root["su-c"], Decimal("3.25"))

        # invalid: non-numeric string should raise ValidationError
        with self.assertRaises(ValidationError):
            usage_models.UsageInfo(root={"su-x": "not-a-number"})

    def test_daily_charges_dict(self):
        # Valid CumulativeChargesDict with YYYY-MM-DD keys
        data = {
            "2025-11-29": {"su1": Decimal("1.0")},
            "2025-11-30": {"su1": Decimal("3.5"), "su2": Decimal("2.0")},
        }
        daily = usage_models.CumulativeChargesDict(root=data)
        # total_charges sums across all dates and SUs
        self.assertEqual(daily.total_charges, Decimal("5.5"))

        # Empty dict -> totals should be zero/empty
        empty = usage_models.CumulativeChargesDict(root={})
        self.assertEqual(empty.total_charges, Decimal("0.0"))

        # Invalid date key format should raise ValidationError
        with self.assertRaises(ValidationError):
            usage_models.CumulativeChargesDict(root={"2025-13-01": {"su": 1.0}})

        with self.assertRaises(ValidationError):
            usage_models.CumulativeChargesDict(root={"2025-01": {"su": 1.0}})

        # Different months should raise ValidationError
        with self.assertRaises(ValidationError):
            usage_models.CumulativeChargesDict(
                root={"2025-12-01": {"su": 1.0}, "2026-12-01": {"su": 1.0}}
            )

    def test_previous_charges_dict(self):
        # Monthly (PreviousChargesDict) requires YYYY-MM keys
        prev_data = {
            "2025-11": {"suA": Decimal("5.0")},
            "2025-12": {"suA": Decimal("2.5"), "suB": Decimal("1.0")},
        }
        prev = usage_models.PreviousChargesDict(root=prev_data)
        self.assertEqual(
            prev.total_charges_by_su,
            {"suA": Decimal("7.5"), "suB": Decimal("1.0")},
        )
        self.assertEqual(prev.total_charges, Decimal("8.5"))

        # Invalid month format should raise ValidationError
        with self.assertRaises(ValidationError):
            usage_models.PreviousChargesDict(root={"2025-11-01": {"su": 1.0}})
