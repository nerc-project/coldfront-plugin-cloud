import io
from unittest import mock

from unittest.mock import Mock, patch


from coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage import (
    Command,
)
from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import usage_models
from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud import utils

from django.core.management import call_command


TEST_INVOICE = """
Project - Allocation ID,SU Type,Cost
test-allocation-1,OpenStack CPU,100.25
test-allocation-1,OpenStack V100 GPU,500.37
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

        usage_info = c.get_allocation_usage("Test", "2025-01-11", "test-allocation-1")
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
