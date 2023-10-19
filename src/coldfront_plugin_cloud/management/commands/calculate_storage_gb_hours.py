import csv
from decimal import Decimal
import dataclasses
from datetime import datetime
import logging

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import utils

from django.core.management.base import BaseCommand
from coldfront.core.resource.models import Resource, ResourceType
from coldfront.core.allocation.models import Allocation, AllocationStatusChoice
import pytz

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class InvoiceRow:
    Interval: str = ""
    Project_Name: str = ""
    Project_ID: str = ""
    PI: str = ""
    Invoice_Email: str = ""
    Invoice_Address : str = ""
    Institution: str = ""
    Institution_Specific_Code: str = ""
    Invoice_Type_Hours: int = 0
    Invoice_Type: str = ""
    Rate: Decimal = 0
    Cost: Decimal = 0


    @classmethod
    def get_headers(cls):
        """Returns all headers for display."""
        return [
            "Interval",
            "Project - Allocation",
            "Project - Allocation ID",
            "Manager (PI)",
            "Invoice Email",
            "Invoice Address",
            "Institution",
            "Institution - Specific Code",
            "SU Hours (GBhr or SUhr)",
            "SU Type",
            "Rate",
            "Cost",
        ]

    def get_value(self, field: str):
        """Returns value for a field.

        :param field: Field to return.
        """
        return getattr(self, field)

    def get_values(self):
        return [
            self.get_value(field.name) for field in dataclasses.fields(self)
        ]


def datetime_type(v):
    return pytz.utc.localize(datetime.strptime(v, '%Y-%m-%d'))


class Command(BaseCommand):
    help = "Generate invoices for storage billing."

    def add_arguments(self, parser):
        parser.add_argument('--start', type=datetime_type, required=True,
                            help='Start period for billing.')
        parser.add_argument('--end', type=datetime_type, required=True,
                            help='End period for billing.')
        parser.add_argument('--output', type=str, default='invoices.csv',
                             help='CSV file to write invoices to.')
        parser.add_argument('--openstack-gb-rate', type=Decimal, required=True,
                            help='Rate for OpenStack Volume and Object GB/hour.')
        parser.add_argument('--openshift-gb-rate', type=Decimal, required=True,
                            help='Rate for OpenShift GB/hour.')

    def handle(self, *args, **options):
        def process_invoice_row(allocation, attribute, price):
            """Calculate the value and write the bill using the writer."""
            time = utils.calculate_quota_unit_hours(
                allocation, attribute, options['start'], options['end']
            )
            billed = time * price
            if billed > 0:
                row = InvoiceRow(
                    Interval=f"{options['start']} - {options['end']}",
                    Project_Name=allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME),
                    Project_ID=allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID),
                    PI=allocation.project.pi,
                    Invoice_Type_Hours=billed,
                    Invoice_Type=attr,
                    Rate=rates[attr],
                    Cost=billed * rates[attr]
                )
                csv_invoice_writer.writerow(
                    row.get_values()
                )

        openstack_resources = Resource.objects.filter(
            resource_type=ResourceType.objects.get(
                name='OpenStack'
            )
        )
        openstack_allocations = Allocation.objects.filter(
            resources__in=openstack_resources
        )
        openshift_resources = Resource.objects.filter(
            resource_type=ResourceType.objects.get(
                name='OpenShift'
            )
        )
        openshift_allocations = Allocation.objects.filter(
            resources__in=openshift_resources
        )

        rates = {
            attributes.QUOTA_VOLUMES_GB: options['openstack_gb_rate'],
            attributes.QUOTA_OBJECT_GB: options['openstack_gb_rate'],
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: options['openshift_gb_rate'],
            attributes.QUOTA_REQUESTS_STORAGE: options['openshift_gb_rate']
        }

        with open(options['output'], 'w', newline='') as f:
            csv_invoice_writer = csv.writer(
                f, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL
            )
            # Write Headers
            csv_invoice_writer.writerow(InvoiceRow.get_headers())

            for allocation in openstack_allocations:
                allocation_str = f'{allocation.pk} of project "{allocation.project.title}"'
                msg = f'Starting billing for for allocation {allocation_str}.'
                logger.debug(msg)

                for attr, price in [
                    (attributes.QUOTA_VOLUMES_GB, 1),
                    (attributes.QUOTA_OBJECT_GB, 1)
                ]:
                    process_invoice_row(allocation, attr, price)

            for allocation in openshift_allocations:
                allocation_str = f'{allocation.pk} of project "{allocation.project.title}"'
                msg = f'Starting billing for for allocation {allocation_str}.'
                logger.debug(msg)

                for attr, price_per_unit in [
                    (attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 1),
                    (attributes.QUOTA_REQUESTS_STORAGE, 1)
                ]:
                    process_invoice_row(allocation, attr, price)
