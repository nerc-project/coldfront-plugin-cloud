from decimal import Decimal
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import functools
import logging
import os
import tempfile
from typing import Optional

from coldfront_plugin_cloud import attributes
from coldfront.core.utils.common import import_from_settings
from coldfront_plugin_cloud import usage_models
from coldfront_plugin_cloud.usage_models import UsageInfo, validate_date_str
from coldfront_plugin_cloud import utils

import boto3
from django.core.management.base import BaseCommand
from coldfront.core.resource.models import Resource
from coldfront.core.allocation.models import Allocation
from coldfront.core.utils import mail
import pandas
import pyarrow
from pandas.core.groupby.generic import DataFrameGroupBy


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RESOURCES_DAILY_ENABLED = ["NERC-OCP", "NERC-EDU", "NERC"]
RESOURCE_NAME_TO_FILE = {
    "NERC": "NERC OpenStack",
    "NERC-OCP": "ocp-prod",
    "NERC-OCP-EDU": "academic",
}
STORAGE_FILE = "NERC Storage"
ALLOCATION_STATES_TO_PROCESS = ["Active", "Active (Needs Renewal)"]

INVOICE_COLUMN_ALLOCATION_ID = "Project - Allocation ID"
INVOICE_COLUMN_SU_TYPE = "SU Type"
INVOICE_COLUMN_COST = "Cost"

S3_KEY_ID = os.getenv("S3_INVOICING_ACCESS_KEY_ID")
S3_SECRET = os.getenv("S3_INVOICING_SECRET_ACCESS_KEY")
S3_ENDPOINT = os.getenv(
    "S3_INVOICING_ENDPOINT_URL", "https://s3.us-east-005.backblazeb2.com"
)
S3_BUCKET = os.getenv("S3_INVOICING_BUCKET", "nerc-invoicing")

CENTER_BASE_URL = import_from_settings("CENTER_BASE_URL")
EMAIL_SENDER = import_from_settings("EMAIL_SENDER")
EMAIL_TEMPLATE = """Dear New England Research Cloud user,

Your {resource.name} {resource.resource_type} Allocation in project {allocation.project.title} has reached your preset Alert value.

- As of midnight last night, your Allocation reached or exceeded your preset Alert value of {alert_value}.
- To view your Allocation information visit {url}/allocation/{allocation.id}

Thank you,
New England Research Cloud (NERC)
https://nerc.mghpcc.org/
"""


@dataclass()
class TotalByDate(object):
    date: str
    total: Decimal

    def __str__(self):
        return f"{self.date}: {self.total} USD"


class Command(BaseCommand):
    help = "Fetch daily billable usage."

    @property
    def previous_day(self):
        return datetime.now(timezone.utc) - timedelta(days=1)

    @property
    def previous_day_string(self):
        return self.previous_day.strftime("%Y-%m-%d")

    def add_arguments(self, parser):
        parser.add_argument(
            "--date", type=str, default=self.previous_day_string, help="Date."
        )

    def handle(self, *args, **options):
        date = options["date"]
        validate_date_str(date)

        allocations = self.get_allocations_for_daily_billing()

        for allocation in allocations:
            resource = allocation.resources.first()
            allocation_project_id = allocation.get_attribute(
                attributes.ALLOCATION_PROJECT_ID
            )

            if not allocation_project_id:
                logger.warning(
                    f"Allocation {allocation.id} is in an active state without a Project ID attribute. Skipping."
                )
                continue

            previous_total = self.get_total_from_attribute(allocation)

            try:
                # We must ensure both the cluster charges for the allocation and the storage
                # charges are both processed otherwise the value will be misleading.
                cluster_usage = self.get_allocation_usage(
                    resource.name, date, allocation_project_id
                )
                storage_usage = self.get_allocation_usage(
                    STORAGE_FILE, date, allocation_project_id
                )
                new_usage = usage_models.merge_models(cluster_usage, storage_usage)
            except Exception as e:
                logger.error(
                    f"Unable to get daily billable usage from {resource.name}, skipping {allocation_project_id}: {e}"
                )
                continue

            # Only update the latest value if the processed date is newer or same date.
            if not previous_total or date >= previous_total.date:
                new_total = TotalByDate(date, new_usage.total_charges)

                self.set_total_on_attribute(allocation, new_total)
                self.handle_alerting(allocation, previous_total, new_total)

    @staticmethod
    def get_daily_location_for_prefix(prefix: str, date: str):
        """Formats the S3 location for a given prefix and date.

        For example, the service invoices for the Resource of type OpenStack and name
        NERC are located in /Invoices/<YYYY-MM>/Service Invoices/NERC OpenStack <YYYY-MM>"""
        return f"Invoices/{usage_models.get_invoice_month_from_date(date)}/Service Invoices/{prefix} {date}.csv"

    @staticmethod
    def get_allocations_for_daily_billing():
        """Fetches all allocations of the production resources that are in the two Active states."""
        return Allocation.objects.filter(
            resources__name__in=RESOURCES_DAILY_ENABLED,
            status__name__in=ALLOCATION_STATES_TO_PROCESS,
        )

    @staticmethod
    def set_total_on_attribute(allocation, total_by_date: TotalByDate):
        """Adds the cumulative charges attribute to a resource."""
        attribute_value = str(total_by_date)
        utils.set_attribute_on_allocation(
            allocation, attributes.ALLOCATION_CUMULATIVE_CHARGES, attribute_value
        )

    @staticmethod
    def get_total_from_attribute(allocation: Allocation) -> Optional[TotalByDate]:
        """Load the total and date from the allocation attribute.

        The format is <YYYY-MM-DD>: <Total> USD"""
        total = allocation.get_attribute(attributes.ALLOCATION_CUMULATIVE_CHARGES)
        if not total:
            return None

        try:
            date, total = total.rstrip(" USD").split(": ")
            return TotalByDate(date=date, total=Decimal(total))
        except ValueError as e:
            logger.warning(
                f"Unable to parse total from attribute for allocation {allocation.id}: {e}"
            )
            return None

    @functools.cached_property
    def s3_client(self):
        if not S3_KEY_ID or not S3_SECRET:
            raise Exception(
                "Must provide S3_INVOICING_ACCESS_KEY_ID and"
                " S3_INVOICING_SECRET_ACCESS_KEY environment variables."
            )

        s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_KEY_ID,
            aws_secret_access_key=S3_SECRET,
        )
        return s3

    @staticmethod
    @functools.cache
    def load_csv(location) -> DataFrameGroupBy:
        df = pandas.read_csv(
            location,
            dtype={INVOICE_COLUMN_COST: pandas.ArrowDtype(pyarrow.decimal128(12, 2))},
        )
        return df.groupby(INVOICE_COLUMN_ALLOCATION_ID)

    @functools.cache
    def load_service_invoice(self, resource: str, date_str: str) -> DataFrameGroupBy:
        """Fetches the dataframe of an invoice from S3."""
        if resource in RESOURCE_NAME_TO_FILE:
            resource = RESOURCE_NAME_TO_FILE[resource]

        key = self.get_daily_location_for_prefix(resource, date_str)
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = os.path.basename(key)
            download_location = os.path.join(tmpdir, filename)
            logger.info(f"Downloading invoice {key} to {download_location}.")
            self.s3_client.download_file(S3_BUCKET, key, download_location)
            return self.load_csv(download_location)

    def get_allocation_usage(
        self, resource: str, date_str: str, allocation_id
    ) -> UsageInfo:
        """Loads the service invoice and parse UsageInfo for a specific allocation."""
        invoice = self.load_service_invoice(resource, date_str)

        try:
            df = invoice.get_group(allocation_id)[
                [INVOICE_COLUMN_SU_TYPE, INVOICE_COLUMN_COST]
            ]
        except KeyError:
            logger.debug(f"No usage for allocation {allocation_id}.")
            return UsageInfo({})

        return UsageInfo(
            df.set_index(INVOICE_COLUMN_SU_TYPE)[INVOICE_COLUMN_COST].to_dict()
        )

    @classmethod
    def handle_alerting(
        cls, allocation, previous_total: TotalByDate, new_total: TotalByDate
    ):
        allocation_alerting_value = allocation.get_attribute(
            attributes.ALLOCATION_ALERT
        )
        already_alerted = False

        if allocation_alerting_value is None:
            # Allocation alerting value attribute is not present on this allocation.
            utils.set_attribute_on_allocation(
                allocation, attributes.ALLOCATION_ALERT, 0
            )
            return

        if allocation_alerting_value <= 0:
            # 0 is the default and does not send any alerts.
            return

        if previous_total and previous_total.total > allocation_alerting_value:
            if usage_models.is_date_same_month(previous_total.date, new_total.date):
                # Alerting value has already been exceeded, do not alert again.
                already_alerted = True

        if new_total.total > allocation_alerting_value:
            logger.info(
                f"{allocation.id} of {allocation.project.title} exceeded"
                f"alerting value of {allocation_alerting_value}."
            )
            if not already_alerted:
                try:
                    cls.send_alert_email(
                        allocation,
                        allocation.get_parent_resource,
                        allocation_alerting_value,
                    )
                    logger.info(
                        f"Sent alert email to PI of {allocation.id} of {allocation.project.title}"
                        f"for exceeding alert value."
                    )
                except Exception as e:
                    logger.error(
                        f"Unable to send alert email to PI of {allocation.id} of {allocation.project.title}: {e}"
                    )

    @staticmethod
    def get_managers(allocation: Allocation):
        """Returns list of managers with enabled notifications."""
        managers_query = allocation.project.projectuser_set.filter(
            role__name="Manager", status__name="Active", enable_notifications=True
        )
        return [manager.user.email for manager in managers_query]

    @classmethod
    def send_alert_email(cls, allocation: Allocation, resource: Resource, alert_value):
        mail.send_email(
            subject="Allocation Usage Alert",
            body=EMAIL_TEMPLATE.format(
                allocation=allocation,
                resource=resource,
                alert_value=alert_value,
                url=CENTER_BASE_URL,
            ),
            sender=EMAIL_SENDER,
            receiver_list=[allocation.project.pi.email],
            cc=cls.get_managers(allocation),
        )
