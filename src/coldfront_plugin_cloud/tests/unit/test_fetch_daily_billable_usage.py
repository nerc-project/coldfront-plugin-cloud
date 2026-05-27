import io
from decimal import Decimal
from unittest import mock

from unittest.mock import Mock, patch


from coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage import (
    Command,
)
from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud.models import usage_models
from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud import utils

from django.core.management import call_command

# Quote char `|` should be read correctly by fetch command
TEST_INVOICE = """
Project - Allocation ID,SU Type,Cost
|test-allocation-1, foo|,OpenStack CPU,100.25
|test-allocation-1, foo|,OpenStack V100 GPU,500.37
test-allocation-2,OpenStack CPU,0.25
"""

OUTPUT_EMAIL_TEMPLATE = """Dear New England Research Cloud user,

Your FakeProd OpenStack Allocation in project FakeProject has reached your preset Alert value.

- As of midnight last night, your Allocation reached or exceeded your preset Alert value of 100.
- To view your Allocation information visit http://localhost/allocation/{allocation_id}

Thank you,
New England Research Cloud (NERC)
https://nerc.mghpcc.org/
"""


class TestFetchDailyBillableUsage(base.TestBase):
    def test_get_daily_location_for_prefix(self):
        self.assertEqual(
            Command.get_daily_location_for_prefix("Test", "2025-11-01"),
            "Invoices/2025-11/Service Invoices/Test 2025-11-01.csv",
        )

    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.Command.s3_client"
    )
    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.Command.load_csv"
    )
    def test_fetch_service_invoice_from_s3(self, mock_load_csv, mock_s3_client):
        c = Command()
        mock_s3_client.download_file = Mock()

        c.load_service_invoice("Test", "2025-11-01")

        self.assertEqual(mock_s3_client.download_file.call_count, 1)
        call_args = mock_s3_client.download_file.call_args[0]
        self.assertEqual(call_args[0], "nerc-invoicing")
        self.assertEqual(
            call_args[1], "Invoices/2025-11/Service Invoices/Test 2025-11-01.csv"
        )

        download_location = call_args[2]
        mock_load_csv.assert_called_once_with(download_location)

    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.Command.load_service_invoice"
    )
    def test_read_csv_and_get_allocation_usage(self, mock_load_service_invoice):
        c = Command()

        # We mock the test CSV with StringIO
        test_invoice_data = io.StringIO(TEST_INVOICE)
        invoice = c.load_csv(test_invoice_data)
        mock_load_service_invoice.return_value = invoice

        usage_info = c.get_allocation_usage(
            "Test", "2025-01-11", "test-allocation-1, foo"
        )
        usage_info_dict = usage_models.to_dict(usage_info)

        self.assertEqual(usage_info_dict["OpenStack CPU"], "100.25")
        self.assertEqual(usage_info_dict["OpenStack V100 GPU"], "500.37")

    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.RESOURCES_DAILY_ENABLED",
        ["FakeProd"],
    )
    def test_get_allocations_for_daily_billing(self):
        fakeprod = self.new_openstack_resource(
            name="FakeProd", internal_name="FakeProd"
        )
        fakedev = self.new_openstack_resource(name="FakeDev", internal_name="FakeDev")

        prod_project = self.new_project()
        dev_project = self.new_project()

        prod_allocation_1 = self.new_allocation(
            project=prod_project, resource=fakeprod, quantity=1, status="Active"
        )
        prod_allocation_2 = self.new_allocation(
            project=prod_project,
            resource=fakeprod,
            quantity=1,
            status="Active (Needs Renewal)",
        )
        prod_allocation_3 = self.new_allocation(
            project=prod_project, resource=fakeprod, quantity=1, status="Denied"
        )

        dev_allocation_1 = self.new_allocation(
            project=dev_project, resource=fakedev, quantity=1, status="Active"
        )

        returned_allocations = Command.get_allocations_for_daily_billing()
        returned_allocation_ids = [x.id for x in returned_allocations]

        self.assertEqual(len(returned_allocations), 2)
        self.assertIn(prod_allocation_1.id, returned_allocation_ids)
        self.assertIn(prod_allocation_2.id, returned_allocation_ids)
        self.assertNotIn(prod_allocation_3, returned_allocation_ids)
        self.assertNotIn(dev_allocation_1, returned_allocation_ids)

    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.RESOURCES_DAILY_ENABLED",
        ["FakeProd"],
    )
    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.Command.get_allocation_usage"
    )
    def test_call_command(self, mock_get_allocation_usage):
        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo({"CPU": "100.00"}),
            usage_models.UsageInfo({"Storage": "30.12"}),
        ]

        fakeprod = self.new_openstack_resource(
            name="FakeProd", internal_name="FakeProd"
        )
        prod_project = self.new_project()
        allocation_1 = self.new_allocation(
            project=prod_project, resource=fakeprod, quantity=1, status="Active"
        )
        utils.set_attribute_on_allocation(
            allocation_1, attributes.ALLOCATION_PROJECT_ID, "test-allocation-1"
        )

        call_command("fetch_daily_billable_usage", date="2025-11-15")

        self.assertEqual(
            allocation_1.get_attribute(attributes.ALLOCATION_CUMULATIVE_CHARGES),
            "2025-11-15: 130.12 USD",
        )

        utils.set_attribute_on_allocation(
            allocation_1, attributes.ALLOCATION_ALERT, 200
        )

        # Testing backfill
        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo({"CPU": "50.00"}),
            usage_models.UsageInfo({"CPU": "30.12"}),
        ]
        call_command("fetch_daily_billable_usage", date="2025-11-14")

        # Previous date doesn't update the allocation attribute
        self.assertEqual(
            allocation_1.get_attribute(attributes.ALLOCATION_CUMULATIVE_CHARGES),
            "2025-11-15: 130.12 USD",
        )

        # Testing reprocessing of same date overwrites previous value.
        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo({"CPU": "40.00"}),
            usage_models.UsageInfo({"Storage": "10.00"}),
        ]
        call_command("fetch_daily_billable_usage", date="2025-11-15")
        self.assertEqual(
            allocation_1.get_attribute(attributes.ALLOCATION_CUMULATIVE_CHARGES),
            "2025-11-15: 50.00 USD",
        )

        # Future date updates the allocation attribute and triggers alerting.
        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo({"CPU": "165.00"}),
            usage_models.UsageInfo({"Storage": "60.00"}),
        ]
        with patch(
            "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.Command.send_alert_email"
        ) as mock:
            call_command("fetch_daily_billable_usage", date="2025-11-16")
            mock.assert_called_once_with(allocation_1, fakeprod, 200)
            self.assertEqual(
                allocation_1.get_attribute(attributes.ALLOCATION_CUMULATIVE_CHARGES),
                "2025-11-16: 225.00 USD",
            )

        # Unable to fetch daily billable usage preserves previous values.
        mock_get_allocation_usage.side_effect = ValueError
        call_command("fetch_daily_billable_usage", date="2025-11-17")
        self.assertEqual(
            allocation_1.get_attribute(attributes.ALLOCATION_CUMULATIVE_CHARGES),
            "2025-11-16: 225.00 USD",
        )

    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.CENTER_BASE_URL",
        "http://localhost",
    )
    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.EMAIL_SENDER",
        "test@example.com",
    )
    def test_send_alert_email(self):
        fakeprod = self.new_openstack_resource(
            name="FakeProd", internal_name="FakeProd"
        )
        prod_project = self.new_project(title="FakeProject")
        allocation_1 = self.new_allocation(
            project=prod_project, resource=fakeprod, quantity=1, status="Active"
        )

        manager = self.new_user()
        self.new_project_user(manager, prod_project, role="Manager")

        normal_user = self.new_user()
        self.new_project_user(normal_user, prod_project, role="User")

        with mock.patch("coldfront.core.utils.mail.send_email") as mock_send_email:
            Command.send_alert_email(
                allocation=allocation_1, resource=fakeprod, alert_value=100
            )
            mock_send_email.assert_called_once_with(
                subject="Allocation Usage Alert",
                body=OUTPUT_EMAIL_TEMPLATE.format(
                    allocation_id=allocation_1.id,
                ),
                sender="test@example.com",
                receiver_list=[allocation_1.project.pi.email],
                cc=[manager.email],
            )

    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.RESOURCES_DAILY_ENABLED",
        ["FakeProd"],
    )
    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.Command.get_allocation_usage"
    )
    def test_database_insertion_and_removal(self, mock_get_allocation_usage):
        """Test database insertion, updates, and removal of usage entries."""
        from coldfront_plugin_cloud.models.daily_billable_usage import AllocationDailyBillableUsage

        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo(
                {"OpenStack CPU": "100.00", "OpenStack GPU": "50.00"}
            ),
            usage_models.UsageInfo({"Storage": "30.12"}),
        ]

        fakeprod = self.new_openstack_resource(
            name="FakeProd", internal_name="FakeProd"
        )
        prod_project = self.new_project()
        allocation_1 = self.new_allocation(
            project=prod_project, resource=fakeprod, quantity=1, status="Active"
        )
        utils.set_attribute_on_allocation(
            allocation_1, attributes.ALLOCATION_PROJECT_ID, "test-allocation-1"
        )

        # Verify no entries before running command
        self.assertEqual(AllocationDailyBillableUsage.objects.count(), 0)

        # Test initial insertion
        call_command("fetch_daily_billable_usage", date="2025-11-15")

        # Verify database entries were created
        usage_entries = AllocationDailyBillableUsage.objects.filter(
            allocation=allocation_1, date="2025-11-15"
        )
        self.assertEqual(usage_entries.count(), 3)

        # Check individual SU types
        cpu_usage = usage_entries.get(su_type="OpenStack CPU")
        self.assertEqual(cpu_usage.value, Decimal("100.00"))

        gpu_usage = usage_entries.get(su_type="OpenStack GPU")
        self.assertEqual(gpu_usage.value, Decimal("50.00"))

        storage_usage = usage_entries.get(su_type="Storage")
        self.assertEqual(storage_usage.value, Decimal("30.12"))

        # Test update_or_create by running again with different values for same date
        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo(
                {"OpenStack CPU": "110.00", "OpenStack GPU": "55.00"}
            ),
            usage_models.UsageInfo({"Storage": "35.00"}),
        ]
        call_command("fetch_daily_billable_usage", date="2025-11-15")

        # Should still have 3 entries (not duplicates)
        usage_entries = AllocationDailyBillableUsage.objects.filter(
            allocation=allocation_1, date="2025-11-15"
        )
        self.assertEqual(usage_entries.count(), 3)

        # Check updated values
        cpu_usage = usage_entries.get(su_type="OpenStack CPU")
        self.assertEqual(cpu_usage.value, Decimal("110.00"))

        # Add data for another date to test selective removal
        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo({"OpenStack CPU": "120.00"}),
            usage_models.UsageInfo({"Storage": "40.00"}),
        ]
        call_command("fetch_daily_billable_usage", date="2025-11-16")

        # Verify data exists for both dates
        self.assertEqual(
            AllocationDailyBillableUsage.objects.filter(date="2025-11-15").count(), 3
        )
        self.assertEqual(
            AllocationDailyBillableUsage.objects.filter(date="2025-11-16").count(), 2
        )

        # Test removal - remove data for 2025-11-15
        call_command("fetch_daily_billable_usage", date="2025-11-15", remove=True)

        # Verify data for 2025-11-15 is deleted
        self.assertEqual(
            AllocationDailyBillableUsage.objects.filter(date="2025-11-15").count(), 0
        )

        # Verify data for 2025-11-16 still exists
        self.assertEqual(
            AllocationDailyBillableUsage.objects.filter(date="2025-11-16").count(), 2
        )

    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.RESOURCES_DAILY_ENABLED",
        ["FakeProd"],
    )
    @patch(
        "coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage.Command.get_allocation_usage"
    )
    def test_multiple_allocations_same_date(self, mock_get_allocation_usage):
        """Test that multiple allocations can store usage for the same date."""
        from coldfront_plugin_cloud.models.daily_billable_usage import AllocationDailyBillableUsage

        fakeprod = self.new_openstack_resource(
            name="FakeProd", internal_name="FakeProd"
        )
        prod_project1 = self.new_project()
        prod_project2 = self.new_project()

        allocation_1 = self.new_allocation(
            project=prod_project1, resource=fakeprod, quantity=1, status="Active"
        )
        allocation_2 = self.new_allocation(
            project=prod_project2, resource=fakeprod, quantity=1, status="Active"
        )

        utils.set_attribute_on_allocation(
            allocation_1, attributes.ALLOCATION_PROJECT_ID, "test-allocation-1"
        )
        utils.set_attribute_on_allocation(
            allocation_2, attributes.ALLOCATION_PROJECT_ID, "test-allocation-2"
        )

        # Mock returns for both allocations
        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo({"OpenStack CPU": "100.00"}),
            usage_models.UsageInfo({"Storage": "30.00"}),
            usage_models.UsageInfo({"OpenStack CPU": "200.00"}),
            usage_models.UsageInfo({"Storage": "50.00"}),
        ]

        call_command("fetch_daily_billable_usage", date="2025-11-15")

        # Verify both allocations have data
        alloc1_entries = AllocationDailyBillableUsage.objects.filter(
            allocation=allocation_1, date="2025-11-15"
        )
        alloc2_entries = AllocationDailyBillableUsage.objects.filter(
            allocation=allocation_2, date="2025-11-15"
        )

        self.assertEqual(alloc1_entries.count(), 2)
        self.assertEqual(alloc2_entries.count(), 2)

        # Verify values are correct for each allocation
        self.assertEqual(
            alloc1_entries.get(su_type="OpenStack CPU").value, Decimal("100.00")
        )
        self.assertEqual(
            alloc2_entries.get(su_type="OpenStack CPU").value, Decimal("200.00")
        )

        # Test updating with same date but different values - should update, not error
        mock_get_allocation_usage.side_effect = [
            usage_models.UsageInfo({"OpenStack CPU": "150.00"}),
            usage_models.UsageInfo({"Storage": "35.00"}),
            usage_models.UsageInfo({"OpenStack CPU": "250.00"}),
            usage_models.UsageInfo({"Storage": "55.00"}),
        ]

        # This should not raise any errors and should update existing values
        call_command("fetch_daily_billable_usage", date="2025-11-15")

        # Verify counts remain the same (no duplicates)
        alloc1_entries = AllocationDailyBillableUsage.objects.filter(
            allocation=allocation_1, date="2025-11-15"
        )
        alloc2_entries = AllocationDailyBillableUsage.objects.filter(
            allocation=allocation_2, date="2025-11-15"
        )

        self.assertEqual(alloc1_entries.count(), 2)
        self.assertEqual(alloc2_entries.count(), 2)

        # Verify values were updated
        self.assertEqual(
            alloc1_entries.get(su_type="OpenStack CPU").value, Decimal("150.00")
        )
        self.assertEqual(alloc1_entries.get(su_type="Storage").value, Decimal("35.00"))
        self.assertEqual(
            alloc2_entries.get(su_type="OpenStack CPU").value, Decimal("250.00")
        )
        self.assertEqual(alloc2_entries.get(su_type="Storage").value, Decimal("55.00"))
