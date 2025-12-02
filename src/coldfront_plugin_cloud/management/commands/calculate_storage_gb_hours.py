import csv
from decimal import Decimal, ROUND_HALF_UP
import dataclasses
from datetime import datetime, timedelta, timezone
import logging
import os

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import utils

import boto3
from django.core.management.base import BaseCommand
from coldfront.core.resource.models import Resource, ResourceType
from coldfront.core.allocation.models import Allocation
import pytz


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_RATES = None


def get_rates():
    # nerc-rates doesn't work with Python 3.9, which is what ColdFront is currently
    # using in Production. Lazily load the rates only when either of the storage rates
    # is not set via CLI arguments, so we can keep providing them via CLI until we upgrade
    # Python version.
    global _RATES

    if _RATES is None:
        from nerc_rates import load_from_url

        _RATES = load_from_url()
    return _RATES


@dataclasses.dataclass
class InvoiceRow:
    InvoiceMonth: str = ""
    Report_Start_Time: str = ""
    Report_End_Time: str = ""
    Project_Name: str = ""
    Project_ID: str = ""
    PI: str = ""
    Cluster_Name: str = ""
    Invoice_Email: str = ""
    Invoice_Address: str = ""
    Institution: str = ""
    Institution_Specific_Code: str = ""
    Invoice_Type_Hours: int = 0
    Invoice_Type: str = ""
    Rate: Decimal = 0
    Cost: Decimal = 0
    Generated_At: str = ""

    @classmethod
    def get_headers(cls):
        """Returns all headers for display."""
        return [
            "Invoice Month",
            "Report Start Time",
            "Report End Time",
            "Project - Allocation",
            "Project - Allocation ID",
            "Manager (PI)",
            "Cluster Name",
            "Invoice Email",
            "Invoice Address",
            "Institution",
            "Institution - Specific Code",
            "SU Hours (GBhr or SUhr)",
            "SU Type",
            "Rate",
            "Cost",
            "Generated At",
        ]

    def get_value(self, field: str):
        """Returns value for a field.

        :param field: Field to return.
        """
        return getattr(self, field)

    def get_values(self):
        return [self.get_value(field.name) for field in dataclasses.fields(self)]


def datetime_type(v):
    return pytz.utc.localize(datetime.fromisoformat(v))


class Command(BaseCommand):
    help = "Generate invoices for storage billing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start",
            type=datetime_type,
            default=self.default_start_argument(),
            help="Start period for billing.",
        )
        parser.add_argument(
            "--end",
            type=datetime_type,
            default=self.default_end_argument(),
            help="End period for billing.",
        )
        parser.add_argument(
            "--invoice-month",
            type=str,
            default=self.default_start_argument().strftime("%Y-%m"),
        )
        parser.add_argument(
            "--output",
            type=str,
            default="invoices.csv",
            help="CSV file to write invoices to.",
        )
        parser.add_argument(
            "--openstack-nese-gb-rate",
            type=Decimal,
            required=False,
            help="Rate for OpenStack NESE Volume and Object GB/hour.",
        )
        parser.add_argument(
            "--openshift-nese-gb-rate",
            type=Decimal,
            required=False,
            help="Rate for OpenShift NESE Storage GB/hour.",
        )
        parser.add_argument(
            "--openshift-ibm-gb-rate",
            type=Decimal,
            required=False,
            help="Rate for OpenShift IBM Storage Scale GB/hour.",
        )
        parser.add_argument(
            "--s3-endpoint-url",
            type=str,
            default="https://s3.us-east-005.backblazeb2.com",
        )
        parser.add_argument("--s3-bucket-name", type=str, default="nerc-invoicing")
        parser.add_argument(
            "--upload-to-s3",
            default=False,
            action="store_true",
            help="Upload generated CSV invoice to S3 storage.",
        )

    @staticmethod
    def default_start_argument():
        d = (datetime.now() - timedelta(days=1)).replace(day=1)
        d = d.replace(hour=0, minute=0, second=0, microsecond=0)
        return pytz.utc.localize(d)

    @staticmethod
    def default_end_argument():
        d = datetime.now()
        d = d.replace(hour=0, minute=0, second=0, microsecond=0)
        return pytz.utc.localize(d)

    @staticmethod
    def upload_to_s3(s3_endpoint, s3_bucket, file_location, invoice_month, end_time):
        s3_key_id = os.getenv("S3_INVOICING_ACCESS_KEY_ID")
        s3_secret = os.getenv("S3_INVOICING_SECRET_ACCESS_KEY")

        if not s3_key_id or not s3_secret:
            raise Exception(
                "Must provide S3_INVOICING_ACCESS_KEY_ID and"
                " S3_INVOICING_SECRET_ACCESS_KEY environment variables."
            )
        if not invoice_month:
            raise Exception("No invoice month specified. Required for S3 upload.")

        s3 = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_key_id,
            aws_secret_access_key=s3_secret,
        )

        primary_location = (
            f"Invoices/{invoice_month}/"
            f"Service Invoices/NERC Storage {invoice_month}.csv"
        )
        s3.upload_file(file_location, Bucket=s3_bucket, Key=primary_location)
        logger.info(f"Uploaded to {primary_location}.")

        # Upload daily copy
        # End time is exclusive, subtract one second to find the inclusive end date
        invoice_date = end_time - timedelta(seconds=1)
        invoice_date = invoice_date.strftime("%Y-%m-%d")
        daily_location = (
            f"Invoices/{invoice_month}/Service Invoices/NERC Storage {invoice_date}.csv"
        )
        s3.upload_file(file_location, Bucket=s3_bucket, Key=daily_location)
        logger.info(f"Uploaded to {daily_location}.")

        # Archival copy
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        secondary_location = (
            f"Invoices/{invoice_month}/"
            f"Archive/NERC Storage {invoice_month} {timestamp}.csv"
        )
        s3.upload_file(file_location, Bucket=s3_bucket, Key=secondary_location)
        logger.info(f"Uploaded to {secondary_location}.")

    def handle(self, *args, **options):
        generated_at = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

        def get_outages_for_service(resource_name: str):
            """Get outages for a service from nerc-rates.

            :param cluster_name: Name of the cluster to get outages for.
            :return: List of excluded intervals or None.
            """
            return utils.load_outages_from_nerc_rates(
                options["start"], options["end"], cluster_name
            )

        def process_invoice_row(allocation, attrs, su_name, rate):
            """Calculate the value and write the bill using the writer."""
            internal_cluster_name = allocation.resources.first().get_attribute(
                attributes.RESOURCE_CLUSTER_NAME
            )
            excluded_intervals_list = get_outages_for_service(internal_cluster_name)

            time = 0
            for attribute in attrs:
                time += utils.calculate_quota_unit_hours(
                    allocation,
                    attribute,
                    options["start"],
                    options["end"],
                    excluded_intervals_list,
                )
            if time > 0:
                row = InvoiceRow(
                    InvoiceMonth=options["invoice_month"],
                    Report_Start_Time=options["start"].isoformat(),
                    Report_End_Time=options["end"].isoformat(),
                    Project_Name=allocation.get_attribute(
                        attributes.ALLOCATION_PROJECT_NAME
                    ),
                    Project_ID=allocation.get_attribute(
                        attributes.ALLOCATION_PROJECT_ID
                    ),
                    PI=allocation.project.pi.email,
                    Cluster_Name=internal_cluster_name,
                    Institution_Specific_Code=allocation.get_attribute(
                        attributes.ALLOCATION_INSTITUTION_SPECIFIC_CODE
                    )
                    or "N/A",
                    Invoice_Type_Hours=time,
                    Invoice_Type=su_name,
                    Rate=rate,
                    Cost=(time * rate).quantize(Decimal(".01"), rounding=ROUND_HALF_UP),
                    Generated_At=generated_at,
                )
                csv_invoice_writer.writerow(row.get_values())

        logger.info(f"Processing invoices for {options['invoice_month']}.")
        logger.info(f"Interval {options['start'] - options['end']}.")

        openstack_resources = Resource.objects.filter(
            resource_type=ResourceType.objects.get(name="OpenStack")
        )
        openstack_allocations = Allocation.objects.filter(
            resources__in=openstack_resources
        )
        openshift_resources = Resource.objects.filter(
            resource_type=ResourceType.objects.get(name="OpenShift")
        )
        openshift_allocations = Allocation.objects.filter(
            resources__in=openshift_resources
        )

        if options["openstack_nese_gb_rate"]:
            openstack_nese_storage_rate = options["openstack_nese_gb_rate"]
        else:
            openstack_nese_storage_rate = get_rates().get_value_at(
                "NESE Storage GB Rate", options["invoice_month"], Decimal
            )

        if options["openshift_nese_gb_rate"]:
            openshift_nese_storage_rate = options["openshift_nese_gb_rate"]
        else:
            openshift_nese_storage_rate = get_rates().get_value_at(
                "NESE Storage GB Rate", options["invoice_month"], Decimal
            )

        if options["openshift_ibm_gb_rate"]:
            openshift_ibm_storage_rate = options["openshift_ibm_gb_rate"]
        else:
            openshift_ibm_storage_rate = get_rates().get_value_at(
                "IBM Spectrum Scale Storage GB Rate", options["invoice_month"], Decimal
            )

        logger.info(
            f"Using storage rate {openstack_nese_storage_rate} (Openstack NESE), {openshift_nese_storage_rate} (Openshift NESE), and "
            f"{openshift_ibm_storage_rate} (Openshift IBM Scale) for {options['invoice_month']}"
        )

        logger.info(f"Writing to {options['output']}.")
        with open(options["output"], "w", newline="") as f:
            csv_invoice_writer = csv.writer(
                f, delimiter=",", quotechar="|", quoting=csv.QUOTE_MINIMAL
            )
            csv_invoice_writer.writerow(InvoiceRow.get_headers())

            for allocation in openstack_allocations:
                allocation_str = (
                    f'{allocation.pk} of project "{allocation.project.title}"'
                )
                logger.debug(f"Starting billing for allocation {allocation_str}.")

                process_invoice_row(
                    allocation,
                    [attributes.QUOTA_VOLUMES_GB, attributes.QUOTA_OBJECT_GB],
                    "OpenStack Storage",
                    openstack_nese_storage_rate,
                )

            for allocation in openshift_allocations:
                allocation_str = (
                    f'{allocation.pk} of project "{allocation.project.title}"'
                )
                logger.debug(f"Starting billing for allocation {allocation_str}.")

                process_invoice_row(
                    allocation,
                    [
                        attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
                        attributes.QUOTA_REQUESTS_NESE_STORAGE,
                    ],
                    "OpenShift NESE Storage",
                    openshift_nese_storage_rate,
                )

                process_invoice_row(
                    allocation,
                    [attributes.QUOTA_REQUESTS_IBM_STORAGE],
                    "OpenShift IBM Scale Storage",
                    openshift_ibm_storage_rate,
                )

        if options["upload_to_s3"]:
            logger.info(f"Uploading to S3 endpoint {options['s3_endpoint_url']}.")
            self.upload_to_s3(
                options["s3_endpoint_url"],
                options["s3_bucket_name"],
                options["output"],
                options["invoice_month"],
                options["end"],
            )
