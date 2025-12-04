import logging

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import utils
from coldfront_plugin_cloud import tasks

from django.core.management.base import BaseCommand
from coldfront.core.resource.models import Resource
from coldfront.core.allocation.models import (
    Allocation,
    AllocationStatusChoice,
)
from keystoneauth1.exceptions import http


logger = logging.getLogger(__name__)

STATES_TO_VALIDATE = ["Active", "Active (Needs Renewal)"]


class Command(BaseCommand):
    help = "Validates quotas and users in resource allocations."

    PLUGIN_RESOURCE_NAMES = [
        "OpenStack",
        "ESI",
        "OpenShift",
        "Openshift Virtualization",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply expected state if validation fails.",
        )

    def check_institution_specific_code(self, allocation, apply):
        attr = attributes.ALLOCATION_INSTITUTION_SPECIFIC_CODE
        isc = allocation.get_attribute(attr)
        if not isc:
            alloc_str = f'{allocation.pk} of project "{allocation.project.title}"'
            msg = f'Attribute "{attr}" missing on allocation {alloc_str}'
            logger.warning(msg)
            if apply:
                utils.set_attribute_on_allocation(allocation, attr, "N/A")
                logger.warning(f'Attribute "{attr}" added to allocation {alloc_str}')

    def handle(self, *args, **options):
        for resource_name in self.PLUGIN_RESOURCE_NAMES:
            resource = Resource.objects.filter(resource_type__name=resource_name)
            allocations = Allocation.objects.filter(
                resources__in=resource,
                status__in=AllocationStatusChoice.objects.filter(
                    name__in=STATES_TO_VALIDATE
                ),
            )

            for allocation in allocations:
                allocator = tasks.find_allocator(allocation)
                logger.debug(
                    f"Starting resource validation for {allocator.allocation_str}."
                )
                self.check_institution_specific_code(allocation, options["apply"])

                project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

                # Check project ID is set
                if not project_id:
                    logger.error(
                        f"{allocator.allocation_str} is active but has no Project ID set."
                    )
                    continue

                # Check project exists in remote cluster
                try:
                    allocator.get_project(project_id)
                except http.NotFound:
                    logger.error(
                        f"{allocator.allocation_str} has Project ID {project_id}. But"
                        f" no project found in {resource_name}."
                    )
                    continue

                allocator.set_project_configuration(project_id, apply=options["apply"])
