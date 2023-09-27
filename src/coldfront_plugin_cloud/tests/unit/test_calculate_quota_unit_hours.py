import datetime
import pytz

import freezegun

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud import utils

from coldfront.core.allocation import models as allocation_models


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
