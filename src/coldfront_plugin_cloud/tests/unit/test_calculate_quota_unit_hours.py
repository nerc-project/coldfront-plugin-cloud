import datetime
import unittest
import pytz

import freezegun

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud import utils

from coldfront.core.allocation import models as allocation_models


SECONDS_IN_DAY = 3600 * 24


class TestCalculateAllocationQuotaHours(base.TestBase):
    def test_new_allocation_quota(self):
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )

        with freezegun.freeze_time("2020-03-15 00:01:00"):
            user = self.new_user()
            project = self.new_project(pi=user)
            allocation = self.new_allocation(project, self.resource, 2)
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)

        with freezegun.freeze_time("2020-03-16 23:59:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 0)

        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 31, 23, 59, 59))
        )
        self.assertEqual(value, 96)


    def test_new_allocation_quota_expired(self):
        """Test that expiration doesn't affect invoicing."""
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)
        allocation.status = allocation_models.AllocationStatusChoice.objects.get(name="Active")

        with freezegun.freeze_time("2020-03-15 00:01:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)

        with freezegun.freeze_time("2020-03-16 23:59:00"):
            allocation.status = allocation_models.AllocationStatusChoice.objects.get(name="Expired")
            allocation.save()

        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 31, 23, 59, 59))
        )
        self.assertEqual(value, 816)

    def test_new_allocation_quota_denied(self):
        """Test a simple case of invoicing until a status change."""
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        with freezegun.freeze_time("2020-03-15 00:01:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)

        with freezegun.freeze_time("2020-03-16 23:59:00"):
            allocation.status = allocation_models.AllocationStatusChoice.objects.get(name="Denied")
            allocation.save()

        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 31, 23, 59, 59))
        )
        self.assertEqual(value, 96)

    def test_new_allocation_quota_last_revoked(self):
        """Test that we correctly distinguish the last transition to an unbilled state."""
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        # Billable
        with freezegun.freeze_time("2020-03-15 00:01:00"):
            allocation.status = allocation_models.AllocationStatusChoice.objects.get(name="New")
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)
            allocation.save()

        allocation.refresh_from_db()

        with freezegun.freeze_time("2020-03-16 23:59:00"):
            allocation.status = allocation_models.AllocationStatusChoice.objects.get(name="Denied")
            allocation.save()

        allocation.refresh_from_db()

        # Billable until here, since this is the last transition into an unbillable status.
        with freezegun.freeze_time("2020-03-17 23:59:00"):
            allocation.status = allocation_models.AllocationStatusChoice.objects.get(name="Revoked")
            allocation.save()

        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 31, 23, 59, 59))
        )
        self.assertEqual(value, 144)

    def test_new_allocation_quota_new(self):
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 4, 1, 0, 0, 0)),
            pytz.utc.localize(datetime.datetime(2020, 5, 1, 0, 0, 0))
        )
        self.assertEqual(value, 0)

    def test_new_allocation_quota_never_approved(self):
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        # We don't set any attributes. This simulates a resource
        # allocation never being approved.

        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 31, 23, 59, 59))
        )
        self.assertEqual(value, 0)

    def test_change_request_decrease(self):
        """Test for when a change request decreases the quota"""
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        with freezegun.freeze_time("2020-03-15 00:00:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)

        with freezegun.freeze_time("2020-03-17 00:00:00"):
            cr = allocation_models.AllocationChangeRequest.objects.create(
                allocation=allocation,
                status = allocation_models.AllocationChangeStatusChoice.objects.filter(
                    name="Approved").first()
            )
            attr = allocation_models.AllocationAttribute.objects.filter(
                allocation_attribute_type__name=attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
                allocation=allocation
            ).first()
            allocation_models.AllocationAttributeChangeRequest.objects.create(
                allocation_change_request=cr,
                allocation_attribute=attr,
                new_value=0,
            )

        with freezegun.freeze_time("2020-03-19 00:00:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 0)
            
        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 31, 23, 59, 59))
        )
        self.assertEqual(value, 96)

    def test_change_request_increase(self):
        """Test for when a change request increases the quota"""
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        with freezegun.freeze_time("2020-03-15 00:00:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)

        with freezegun.freeze_time("2020-03-17 00:00:00"):
            cr = allocation_models.AllocationChangeRequest.objects.create(
                allocation=allocation,
                status = allocation_models.AllocationChangeStatusChoice.objects.filter(
                    name="Approved").first()
            )
            attr = allocation_models.AllocationAttribute.objects.filter(
                allocation_attribute_type__name=attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
                allocation=allocation
            ).first()
            allocation_models.AllocationAttributeChangeRequest.objects.create(
                allocation_change_request=cr,
                allocation_attribute=attr,
                new_value=4,
            )

        with freezegun.freeze_time("2020-03-19 00:00:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 4)
            
        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 20, 23, 59, 59))
        )
        self.assertEqual(value, 384)

    def test_change_request_decrease_multiple(self):
        """Test for when multiple different change request decreases the quota"""
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        with freezegun.freeze_time("2020-03-15 00:00:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)
            
        # In this case, approved CR is the first CR submitted
        with freezegun.freeze_time("2020-03-16 00:00:00"):
            cr = allocation_models.AllocationChangeRequest.objects.create(
                allocation=allocation,
                status = allocation_models.AllocationChangeStatusChoice.objects.filter(
                    name="Approved").first()
            )
            attr = allocation_models.AllocationAttribute.objects.filter(
                allocation_attribute_type__name=attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
                allocation=allocation
            ).first()
            allocation_models.AllocationAttributeChangeRequest.objects.create(
                allocation_change_request=cr,
                allocation_attribute=attr,
                new_value=0,
            )

        with freezegun.freeze_time("2020-03-17 00:00:00"):
            cr = allocation_models.AllocationChangeRequest.objects.create(
                allocation=allocation,
                status = allocation_models.AllocationChangeStatusChoice.objects.filter(
                    name="Approved").first()
            )
            attr = allocation_models.AllocationAttribute.objects.filter(
                allocation_attribute_type__name=attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
                allocation=allocation
            ).first()
            allocation_models.AllocationAttributeChangeRequest.objects.create(
                allocation_change_request=cr,
                allocation_attribute=attr,
                new_value=1,
            )

        with freezegun.freeze_time("2020-03-19 00:00:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 0)
            
        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 31, 23, 59, 59))
        )
        self.assertEqual(value, 48)

    def test_new_allocation_quota_change_request(self):
        self.resource = self.new_openshift_resource(
            name="",
            auth_url="",
        )
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        with freezegun.freeze_time("2020-03-15 00:01:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)

        with freezegun.freeze_time("2020-03-16 23:59:00"):
            cr = allocation_models.AllocationChangeRequest.objects.create(
                allocation=allocation,
                status = allocation_models.AllocationChangeStatusChoice.objects.filter(
                    name="Approved").first()
            )
            attr = allocation_models.AllocationAttribute.objects.filter(
                allocation_attribute_type__name=attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
                allocation=allocation
            ).first()
            allocation_models.AllocationAttributeChangeRequest.objects.create(
                allocation_change_request=cr,
                allocation_attribute=attr,
                new_value=0,
            )

        with freezegun.freeze_time("2020-03-17 23:59:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 0)

        with freezegun.freeze_time("2020-03-18 23:59:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 2)

        with freezegun.freeze_time("2020-03-19 23:59:00"):
            utils.set_attribute_on_allocation(
                allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 0)

        allocation.refresh_from_db()

        value = utils.calculate_quota_unit_hours(
            allocation,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            pytz.utc.localize(datetime.datetime(2020, 3, 1, 0, 0, 1)),
            pytz.utc.localize(datetime.datetime(2020, 3, 31, 23, 59, 59))
        )
        self.assertEqual(value, 144)

    def test_calculate_time_excluded_intervals(self):
        """Test get_included_duration for correctness"""
        def get_excluded_interval_datetime_list(excluded_interval_list):
            return [
                [datetime.datetime(t1[0], t1[1], t1[2], 0, 0, 0), 
                datetime.datetime(t2[0], t2[1], t2[2], 0, 0, 0)] 
                for t1, t2 in excluded_interval_list
            ]

        # Single interval within active period
        excluded_intervals = [
            (datetime.datetime(2020, 3, 15, 9, 30, 0),
             datetime.datetime(2020, 3, 16, 10, 30, 0)),
        ]

        value = utils.get_included_duration(
            datetime.datetime(2020, 3, 15, 0, 0, 0),
            datetime.datetime(2020, 3, 17, 0, 0, 0),
            excluded_intervals
        )
        self.assertEqual(value, SECONDS_IN_DAY * 1 - 3600)

        # Interval starts before active period
        excluded_intervals = get_excluded_interval_datetime_list(
            (((2020, 3, 13), (2020, 3, 16)),)
        )
        value = utils.get_included_duration(
            datetime.datetime(2020, 3, 15, 0, 0, 0),
            datetime.datetime(2020, 3, 18, 0, 0, 0),
            excluded_intervals
        )
        self.assertEqual(value, SECONDS_IN_DAY * 2)

        # Interval ending after active period
        excluded_intervals = get_excluded_interval_datetime_list(
            (((2020, 3, 16), (2020, 3, 18)),)
        )
        value = utils.get_included_duration(
            datetime.datetime(2020, 3, 15, 0, 0, 0),
            datetime.datetime(2020, 3, 17, 0, 0, 0),
            excluded_intervals
        )
        self.assertEqual(value, SECONDS_IN_DAY)

        # Intervals outside active period
        excluded_intervals = get_excluded_interval_datetime_list(
            (((2020, 3, 1), (2020, 3, 5)),
             ((2020, 3, 10), (2020, 3, 11)),
             ((2020, 3, 20), (2020, 3, 25)),)
        )
        value = utils.get_included_duration(
            datetime.datetime(2020, 3, 12, 0, 0, 0),
            datetime.datetime(2020, 3, 19, 0, 0, 0),
            excluded_intervals
        )
        self.assertEqual(value, SECONDS_IN_DAY * 7)

        # Multiple intervals in and out of active period
        excluded_intervals = get_excluded_interval_datetime_list(
            (((2020, 3, 13), (2020, 3, 15)),
             ((2020, 3, 16), (2020, 3, 17)),
             ((2020, 3, 18), (2020, 3, 20)),)
        )
        value = utils.get_included_duration(
            datetime.datetime(2020, 3, 14, 0, 0, 0),
            datetime.datetime(2020, 3, 19, 0, 0, 0),
            excluded_intervals
        )
        self.assertEqual(value, SECONDS_IN_DAY * 2)

        # Interval completely excluded
        excluded_intervals = get_excluded_interval_datetime_list(
            (((2020, 3, 1), (2020, 3, 30)),)
        )
        value = utils.get_included_duration(
            datetime.datetime(2020, 3, 14, 0, 0, 0),
            datetime.datetime(2020, 3, 18, 0, 0, 0),
            excluded_intervals
        )
        self.assertEqual(value, 0)

    def test_load_excluded_intervals(self):
        """Test load_excluded_intervals returns valid output"""

        # Single interval
        interval_list = [
            "2023-01-01,2023-01-02"
        ]
        output = utils.load_excluded_intervals(interval_list)
        self.assertEqual(output, [
            [datetime.datetime(2023, 1, 1, 0, 0, 0),
            datetime.datetime(2023, 1, 2, 0, 0, 0)]
        ])

        # More than 1 interval
        interval_list = [
            "2023-01-01,2023-01-02",
            "2023-01-04 09:00:00,2023-01-15 10:00:00",
        ]
        output = utils.load_excluded_intervals(interval_list)
        self.assertEqual(output, [
            [datetime.datetime(2023, 1, 1, 0, 0, 0),
            datetime.datetime(2023, 1, 2, 0, 0, 0)],
            [datetime.datetime(2023, 1, 4, 9, 0, 0),
            datetime.datetime(2023, 1, 15, 10, 0, 0)]
        ])

    def test_load_excluded_intervals_invalid(self):
        """Test when given invalid time intervals"""

        # First interval is invalid
        invalid_interval = ["foo"]
        with self.assertRaises(ValueError):
            utils.load_excluded_intervals(invalid_interval)

        # First interval is valid, but not second
        invalid_interval = ["2001-01-01,2002-01-01", "foo,foo"]
        with self.assertRaises(ValueError):
            utils.load_excluded_intervals(invalid_interval)

        # End date is before start date
        invalid_interval = ["2000-10-01,2000-01-01"]
        with self.assertRaises(AssertionError):
            utils.load_excluded_intervals(invalid_interval)

        # Overlapping intervals
        invalid_interval = [
            "2000-01-01,2000-01-04",
            "2000-01-02,2000-01-06",                
        ]
        with self.assertRaises(AssertionError):
            utils.load_excluded_intervals(invalid_interval)
