import csv
from datetime import datetime
import logging
import sys

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import utils

from novaclient import client as novaclient
from django.core.management.base import BaseCommand
from coldfront.core.resource.models import Resource, ResourceType
from coldfront.core.allocation.models import Allocation, AllocationStatusChoice
import pytz

logger = logging.getLogger(__name__)


def datetime_type(v):
    return pytz.utc.localize(datetime.strptime(v, '%Y-%m-%d'))


class Command(BaseCommand):
    help = "Generate invoices for storage billing."

    def add_arguments(self, parser):
        parser.add_argument('--start', type=datetime_type, required=True,
                            help='Start period for billing.')
        parser.add_argument('--end', type=datetime_type, required=True,
                            help='End period for billing.')

    def handle(self, *args, **options):
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

        with open('invoices.csv', 'w', newline='') as f:
            csv_invoice_writer = csv.writer(
                f, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL
            )
            # Write Headers
            csv_invoice_writer.writerow(
                [
                    "Interval",
                    "Project Name",
                    "Project ID",
                    "PI",
                    "Invoice Email",
                    "Invoice Address",
                    "Institution",
                    "Institution Specific Code",
                    "Invoice Type Hours",
                    "Invoice Type",
                    "Rate",
                    "Cost",
                ]
            )

            for allocation in openstack_allocations:
                allocation_str = f'{allocation.pk} of project "{allocation.project.title}"'
                msg = f'Starting billing for for allocation {allocation_str}.'
                logger.debug(msg)

                for attr, price_per_unit in [
                    (attributes.QUOTA_VOLUMES_GB, 1),
                    (attributes.QUOTA_OBJECT_GB, 1)
                ]:
                    time = utils.calculate_quota_unit_hours(
                        allocation, attr, options['start'], options['end']
                    )
                    billed = time * price_per_unit
                    if billed > 0:
                        csv_invoice_writer.writerow(
                            [
                                f"{options['start']} - {options['end']}",
                                allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME),
                                allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID),
                                allocation.project.pi,
                                "",  # Invoice Email
                                "",  # Invoice Address
                                "",  # Institutions
                                "",  # Institution Specific Code
                                billed,
                                attr,
                                "",  # Rate
                                "",  # Cost
                            ]
                        )

            for allocation in openshift_allocations:
                allocation_str = f'{allocation.pk} of project "{allocation.project.title}"'
                msg = f'Starting billing for for allocation {allocation_str}.'
                logger.debug(msg)

                for attr, price_per_unit in [
                    (attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 1)
                ]:
                    time = utils.calculate_quota_unit_hours(
                        allocation, attr, options['start'], options['end']
                    )
                    billed = time * price_per_unit
                    if billed > 0:
                        csv_invoice_writer.writerow(
                            [
                                f"{options['start']} - {options['end']}",
                                allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME),
                                allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID),
                                allocation.project.pi,
                                "",  # Invoice Email
                                "",  # Invoice Address
                                "",  # Institutions
                                "",  # Institution Specific Code
                                billed,
                                attr,
                                "",  # Rate
                                "",  # Cost
                            ]
                        )
