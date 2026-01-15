import logging

from coldfront_plugin_cloud import attributes

from django.core.management.base import BaseCommand
from django.core.management import call_command
from coldfront.core.resource.models import Resource, ResourceType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """One time command to migrate quotas to each Openshift and Openstack resource"""

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the migration. Without this flag, only shows what would be done (dry run).",
        )

    def handle(self, *args, **options):
        apply_migration = options.get("apply", False)

        if not apply_migration:
            logger.info(
                self.style.WARNING(
                    "DRY RUN MODE: No changes will be made. Use --apply to apply the migration."
                )
            )

        # Define quotas for each resource type
        openshift_quotas = [
            {
                "display_name": attributes.QUOTA_LIMITS_CPU,
                "quota_label": "limits.cpu",
                "multiplier": 1,
            },
            {
                "display_name": attributes.QUOTA_LIMITS_MEMORY,
                "quota_label": "limits.memory",
                "multiplier": 4096,
                "unit_suffix": "Mi",
            },
            {
                "display_name": attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
                "quota_label": "limits.ephemeral-storage",
                "multiplier": 5,
                "unit_suffix": "Gi",
            },
            {
                "display_name": attributes.QUOTA_PVC,
                "quota_label": "persistentvolumeclaims",
                "multiplier": 2,
            },
            {
                "display_name": attributes.QUOTA_REQUESTS_NESE_STORAGE,
                "quota_label": "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage",
                "multiplier": 20,
                "static_quota": 0,
                "unit_suffix": "Gi",
            },
            {
                "display_name": attributes.QUOTA_REQUESTS_GPU,
                "quota_label": "requests.nvidia.com/gpu",
                "multiplier": 0,
            },
        ]

        openstack_quotas = [
            {
                "display_name": attributes.QUOTA_INSTANCES,
                "quota_label": "instances",
                "multiplier": 1,
                "resource_type": "compute",
            },
            {
                "display_name": attributes.QUOTA_VCPU,
                "quota_label": "cores",
                "multiplier": 1,
                "resource_type": "compute",
            },
            {
                "display_name": attributes.QUOTA_RAM,
                "quota_label": "ram",
                "multiplier": 4096,
                "resource_type": "compute",
            },
            {
                "display_name": attributes.QUOTA_VOLUMES,
                "quota_label": "volumes",
                "multiplier": 2,
                "resource_type": "volume",
            },
            {
                "display_name": attributes.QUOTA_VOLUMES_GB,
                "quota_label": "gigabytes",
                "multiplier": 20,
                "resource_type": "volume",
            },
            {
                "display_name": attributes.QUOTA_FLOATING_IPS,
                "quota_label": "floatingip",
                "multiplier": 0,
                "static_quota": 2,
                "resource_type": "network",
            },
            {
                "display_name": attributes.QUOTA_OBJECT_GB,
                "quota_label": "x-account-meta-quota-bytes",
                "multiplier": 1,
                "resource_type": "object",
            },
        ]

        # Find OpenShift resources
        try:
            openshift_resource_type = ResourceType.objects.get(name="OpenShift")
            openshift_resources = Resource.objects.filter(
                resource_type=openshift_resource_type
            )
        except ResourceType.DoesNotExist:
            openshift_resources = []

        # Find OpenStack resources
        try:
            openstack_resource_type = ResourceType.objects.get(name="OpenStack")
            openstack_resources = Resource.objects.filter(
                resource_type=openstack_resource_type
            )
        except ResourceType.DoesNotExist:
            openstack_resources = []

        # Process OpenShift resources
        for resource in openshift_resources:
            logger.info(f"Processing OpenShift resource: {resource.name}")
            for quota_info in openshift_quotas:
                self._add_quota_to_resource(resource, quota_info, apply_migration)

        # Process OpenStack resources
        for resource in openstack_resources:
            logger.info(f"Processing OpenStack resource: {resource.name}")
            for quota_info in openstack_quotas:
                self._add_quota_to_resource(resource, quota_info, apply_migration)

    def _add_quota_to_resource(self, resource, quota_info, apply_migration):
        """Add a quota to a resource"""
        display_name = quota_info["display_name"]
        logger.info(f"Adding {display_name} to {resource.name}")

        if apply_migration:
            try:
                call_command(
                    "add_quota_to_resource", resource_name=resource.name, **quota_info
                )
            except Exception as e:
                logger.error(
                    f"Error adding {display_name} to {resource.name}: {str(e)}"
                )
