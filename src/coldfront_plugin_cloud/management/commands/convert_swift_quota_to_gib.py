import logging

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import openstack

from django.core.management.base import BaseCommand
from django.db.models import Q
from coldfront.core.resource.models import Resource, ResourceType
from coldfront.core.allocation.models import Allocation, AllocationStatusChoice

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """One time command to convert all Swift quotas on all Openstack allocations from
    GB to GiB. I.e a Swift quota of 1000^2 bytes will now be 1024^2 bytes"""

    def handle(self, *args, **options):
        openstack_resources = Resource.objects.filter(
            resource_type=ResourceType.objects.get(name="OpenStack")
        )
        openstack_allocations = Allocation.objects.filter(
            Q(status=AllocationStatusChoice.objects.get(name="Active"))
            | Q(status=AllocationStatusChoice.objects.get(name="Expired")),
            resources__in=openstack_resources,
        )
        for allocation in openstack_allocations:
            if not (
                swift_quota := allocation.get_attribute(attributes.QUOTA_OBJECT_GB)
            ):
                continue

            allocation_str = f'{allocation.pk} of project "{allocation.project.title}"'
            obj_key = openstack.QUOTA_KEY_MAPPING["object"]["keys"][
                attributes.QUOTA_OBJECT_GB
            ]
            allocator = openstack.OpenStackResourceAllocator(
                allocation.resources.first(), allocation
            )

            project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
            if not project_id:
                logger.error(f"{allocation_str} is active but has no Project ID set.")
                continue
            payload = {obj_key: swift_quota}

            allocator._set_object_quota(project_id, payload)
