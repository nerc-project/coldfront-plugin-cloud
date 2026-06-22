from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from coldfront.core.allocation.models import Allocation
from coldfront_plugin_cloud.billable_usage import (
    _rows_to_usage_info,
    get_daily_billable_usage_by_date,
)
from coldfront_plugin_cloud.models.daily_billable_usage import (
    AllocationDailyBillableUsage,
)
from coldfront_plugin_cloud.models.usage_models import UsageInfo
from coldfront_plugin_cloud.tests import base


class TestRowsToUsageInfo(base.TestBase):
    def _new_allocation(self):
        resource = self.new_openstack_resource()
        project = self.new_project()
        return self.new_allocation(project=project, resource=resource, quantity=1)

    def test_empty_iterable(self):
        usage = _rows_to_usage_info([])
        self.assertEqual(usage, UsageInfo({}))

    def test_multiple_rows(self):
        rows = [
            AllocationDailyBillableUsage(su_type="OpenStack CPU", value=Decimal("100")),
            AllocationDailyBillableUsage(su_type="Storage", value=Decimal("30.12")),
        ]
        expected = UsageInfo(
            {"OpenStack CPU": Decimal("100"), "Storage": Decimal("30.12")}
        )
        self.assertEqual(_rows_to_usage_info(rows), expected)

    def test_rows_is_none(self):
        with self.assertRaises(TypeError):
            _rows_to_usage_info(None)

    def test_non_model_row(self):
        with self.assertRaises(AttributeError):
            _rows_to_usage_info(["not-a-row"])

    def test_empty_su_type(self):
        # Enforce that every row has a usable key; empty SU type would corrupt the usage dict.
        allocation = self._new_allocation()
        row = AllocationDailyBillableUsage.objects.create(
            allocation=allocation,
            date="2025-11-15",
            su_type="",
            value=Decimal("1.00"),
        )
        with self.assertRaises(ValueError) as ctx:
            _rows_to_usage_info([row])
        self.assertIn(f"id={row.pk}", str(ctx.exception))


class TestGetDailyBillableUsage(base.TestBase):
    def _new_allocation(self):
        resource = self.new_openstack_resource()
        project = self.new_project()
        return self.new_allocation(project=project, resource=resource, quantity=1)

    def _create_usage_row(self, allocation, date, su_type, value):
        return AllocationDailyBillableUsage.objects.create(
            allocation=allocation,
            date=date,
            su_type=su_type,
            value=Decimal(value),
        )

    def _get_usage_for_date(self, allocation, date):
        return get_daily_billable_usage_by_date(allocation, date, date).get(
            date, UsageInfo({})
        )

    def test_happy_path(self):
        allocation = self._new_allocation()
        date = "2025-11-15"
        self._create_usage_row(allocation, date, "OpenStack CPU", "100.00")
        self._create_usage_row(allocation, date, "OpenStack V100 GPU", "50.00")
        self._create_usage_row(allocation, date, "Storage", "30.12")

        expected = UsageInfo(
            {
                "OpenStack CPU": Decimal("100.00"),
                "OpenStack V100 GPU": Decimal("50.00"),
                "Storage": Decimal("30.12"),
            }
        )
        self.assertEqual(self._get_usage_for_date(allocation, date), expected)

    def test_no_rows_returns_empty_usage_info(self):
        allocation = self._new_allocation()
        date = "2025-11-15"
        self.assertEqual(self._get_usage_for_date(allocation, date), UsageInfo({}))

    def test_wrong_allocation_type(self):
        date = "2025-11-15"
        with self.assertRaises(AttributeError):
            get_daily_billable_usage_by_date("not-an-allocation", date, date)

    def test_unsaved_allocation(self):
        allocation = Allocation()
        date = "2025-11-15"
        with self.assertRaises(ValueError) as ctx:
            get_daily_billable_usage_by_date(allocation, date, date)
        self.assertIn("primary key", str(ctx.exception))

    def test_empty_date(self):
        allocation = self._new_allocation()
        with self.assertRaises(ValueError):
            get_daily_billable_usage_by_date(allocation, "", "")

    def test_whitespace_date(self):
        allocation = self._new_allocation()
        with self.assertRaises(ValueError):
            get_daily_billable_usage_by_date(allocation, "   ", "   ")

    def test_invalid_date(self):
        allocation = self._new_allocation()
        with self.assertRaises(ValueError):
            get_daily_billable_usage_by_date(allocation, "2025-13-01", "2025-13-01")

    def test_excludes_other_allocation_and_date(self):
        allocation = self._new_allocation()
        other_allocation = self._new_allocation()
        date = "2025-11-15"
        self._create_usage_row(allocation, date, "OpenStack CPU", "100.00")
        self._create_usage_row(allocation, "2025-11-16", "OpenStack CPU", "200.00")
        self._create_usage_row(other_allocation, date, "OpenStack CPU", "999.00")

        expected = UsageInfo({"OpenStack CPU": Decimal("100.00")})
        self.assertEqual(self._get_usage_for_date(allocation, date), expected)


class TestGetDailyBillableUsageByDate(base.TestBase):
    def _new_allocation(self):
        resource = self.new_openstack_resource()
        project = self.new_project()
        return self.new_allocation(project=project, resource=resource, quantity=1)

    def _create_usage_row(self, allocation, date, su_type, value):
        return AllocationDailyBillableUsage.objects.create(
            allocation=allocation,
            date=date,
            su_type=su_type,
            value=Decimal(value),
        )

    def test_groups_usage_by_date(self):
        allocation = self._new_allocation()
        self._create_usage_row(allocation, "2025-11-01", "OpenStack CPU", "10.00")
        self._create_usage_row(allocation, "2025-11-01", "Storage", "5.50")
        self._create_usage_row(allocation, "2025-11-02", "OpenStack CPU", "22.50")
        self._create_usage_row(allocation, "2025-10-31", "OpenStack CPU", "99.00")

        expected = {
            "2025-11-01": UsageInfo(
                {"OpenStack CPU": Decimal("10.00"), "Storage": Decimal("5.50")}
            ),
            "2025-11-02": UsageInfo({"OpenStack CPU": Decimal("22.50")}),
        }
        self.assertEqual(
            get_daily_billable_usage_by_date(allocation, "2025-11-01", "2025-11-30"),
            expected,
        )

    def test_empty_when_no_matching_rows(self):
        allocation = self._new_allocation()
        usage_by_date = get_daily_billable_usage_by_date(
            allocation, "2025-11-01", "2025-11-30"
        )
        self.assertEqual(usage_by_date, {})

    def test_start_date_after_end_date(self):
        allocation = self._new_allocation()
        with self.assertRaises(ValueError):
            get_daily_billable_usage_by_date(allocation, "2025-11-30", "2025-11-01")

    def test_unsaved_allocation(self):
        allocation = Allocation()
        with self.assertRaises(ValueError):
            get_daily_billable_usage_by_date(allocation, "2025-11-01", "2025-11-30")


class TestAllocationDailyBillableUsageModel(base.TestBase):
    def _new_allocation(self):
        resource = self.new_openstack_resource()
        project = self.new_project()
        return self.new_allocation(project=project, resource=resource, quantity=1)

    def _create_usage_row(self, allocation, date, su_type, value):
        return AllocationDailyBillableUsage.objects.create(
            allocation=allocation,
            date=date,
            su_type=su_type,
            value=Decimal(value),
        )

    def test_str(self):
        # A stable __str__ helps debugging/logging/admin views when inspecting usage rows.
        allocation = self._new_allocation()
        row = self._create_usage_row(
            allocation, "2025-11-15", "OpenStack CPU", "100.00"
        )
        self.assertEqual(
            str(row),
            f"{allocation.id} - 2025-11-15 - OpenStack CPU: 100.00",
        )

    def test_unique_together_raises_on_duplicate(self):
        # Enforce one row per (allocation, date, su_type) so upserts don't create duplicates.
        allocation = self._new_allocation()
        self._create_usage_row(allocation, "2025-11-15", "OpenStack CPU", "100.00")
        with self.assertRaises(IntegrityError):
            AllocationDailyBillableUsage.objects.create(
                allocation=allocation,
                date="2025-11-15",
                su_type="OpenStack CPU",
                value=Decimal("200.00"),
            )

    def test_allocation_delete_cascades_to_usage_rows(self):
        # Foreign key cascade prevents orphaned usage rows when an allocation is deleted.
        allocation = self._new_allocation()
        self._create_usage_row(allocation, "2025-11-15", "OpenStack CPU", "100.00")
        self._create_usage_row(allocation, "2025-11-16", "Storage", "30.00")
        self.assertEqual(AllocationDailyBillableUsage.objects.count(), 2)

        allocation.delete()

        self.assertEqual(AllocationDailyBillableUsage.objects.count(), 0)

    def test_meta_ordering(self):
        # Ordering affects deterministic reads/merges; this locks the contract to the model definition.
        self.assertEqual(
            AllocationDailyBillableUsage._meta.ordering,
            ["-date", "allocation", "su_type"],
        )
        allocation_a = self._new_allocation()
        allocation_b = self._new_allocation()
        self._create_usage_row(allocation_a, "2025-11-01", "Storage", "10.00")
        self._create_usage_row(allocation_a, "2025-11-15", "OpenStack CPU", "20.00")
        self._create_usage_row(allocation_b, "2025-11-15", "OpenStack CPU", "30.00")

        rows = list(AllocationDailyBillableUsage.objects.all())
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].date.isoformat(), "2025-11-15")
        self.assertEqual(rows[1].date.isoformat(), "2025-11-15")
        self.assertEqual(rows[2].date.isoformat(), "2025-11-01")
        # Same date: ordering uses Allocation model default ordering via FK.
        nov_15_allocation_ids = {rows[0].allocation_id, rows[1].allocation_id}
        self.assertEqual(nov_15_allocation_ids, {allocation_a.id, allocation_b.id})

    def test_value_stores_two_decimal_places(self):
        # Value is money-like and must round-trip without float precision loss.
        allocation = self._new_allocation()
        row = self._create_usage_row(allocation, "2025-11-15", "Storage", "30.12")
        row.refresh_from_db()
        self.assertEqual(row.value, Decimal("30.12"))

    def test_value_rejects_overflow_beyond_max_digits(self):
        # Schema protection: reject invoice values that exceed the declared DecimalField size.
        allocation = self._new_allocation()
        row = AllocationDailyBillableUsage(
            allocation=allocation,
            date="2025-11-15",
            su_type="OpenStack CPU",
            value=Decimal("10000000000.00"),
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_timestamps_set_on_create_and_modified_on_update(self):
        # TimeStampedModel should set created/modified and advance modified on updates.
        allocation = self._new_allocation()
        row = self._create_usage_row(
            allocation, "2025-11-15", "OpenStack CPU", "100.00"
        )
        created_at = row.created
        modified_at = row.modified
        self.assertIsNotNone(created_at)
        self.assertIsNotNone(modified_at)

        later = timezone.now() + timedelta(seconds=1)
        with mock.patch("django.utils.timezone.now", return_value=later):
            row.value = Decimal("150.00")
            row.save()
        row.refresh_from_db()

        self.assertEqual(row.created, created_at)
        self.assertGreater(row.modified, modified_at)

    def test_related_name_daily_usage_records(self):
        # Reverse relation is the primary way callers will traverse allocation -> daily usage rows.
        allocation = self._new_allocation()
        other_allocation = self._new_allocation()
        self._create_usage_row(allocation, "2025-11-15", "OpenStack CPU", "100.00")
        self._create_usage_row(allocation, "2025-11-16", "Storage", "30.00")
        self._create_usage_row(
            other_allocation, "2025-11-15", "OpenStack CPU", "999.00"
        )

        self.assertEqual(allocation.daily_usage_records.count(), 2)
        self.assertEqual(
            allocation.daily_usage_records.filter(date="2025-11-15").count(),
            1,
        )
        self.assertEqual(
            allocation.daily_usage_records.get(date="2025-11-15").value,
            Decimal("100.00"),
        )
