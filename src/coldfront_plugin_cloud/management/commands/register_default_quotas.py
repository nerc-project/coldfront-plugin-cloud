import logging

from coldfront_plugin_cloud import attributes

from django.core.management.base import BaseCommand
from django.core.management import call_command
from coldfront.core.resource.models import Resource

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STORAGE_RESOURCE_TYPE_NAME = "storage"
OPENSHIFT_STORAGE_INVOICE_NAME = "OpenShift NESE Storage"
OPENSTACK_STORAGE_INVOICE_NAME = "OpenStack Storage"


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
                "resource_type": STORAGE_RESOURCE_TYPE_NAME,
                "invoice_name": OPENSHIFT_STORAGE_INVOICE_NAME,
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
                "resource_type": STORAGE_RESOURCE_TYPE_NAME,
                "invoice_name": OPENSHIFT_STORAGE_INVOICE_NAME,
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
                "quota_label": "compute.instances",
                "multiplier": 1,
            },
            {
                "display_name": attributes.QUOTA_VCPU,
                "quota_label": "compute.cores",
                "multiplier": 1,
            },
            {
                "display_name": attributes.QUOTA_RAM,
                "quota_label": "compute.ram",
                "multiplier": 4096,
            },
            {
                "display_name": attributes.QUOTA_VOLUMES,
                "quota_label": "volume.volumes",
                "multiplier": 2,
            },
            {
                "display_name": attributes.QUOTA_VOLUMES_GB,
                "quota_label": "volume.gigabytes",
                "multiplier": 20,
                "resource_type": STORAGE_RESOURCE_TYPE_NAME,
                "invoice_name": OPENSTACK_STORAGE_INVOICE_NAME,
            },
            {
                "display_name": attributes.QUOTA_FLOATING_IPS,
                "quota_label": "network.floatingip",
                "multiplier": 0,
                "static_quota": 2,
            },
            {
                "display_name": attributes.QUOTA_OBJECT_GB,
                "quota_label": "object.x-account-meta-quota-bytes",
                "multiplier": 1,
                "resource_type": STORAGE_RESOURCE_TYPE_NAME,
                "invoice_name": OPENSTACK_STORAGE_INVOICE_NAME,
            },
            {
                "display_name": attributes.QUOTA_GPU,
                "quota_label": "internal.",
            },
        ]

        # Find OpenShift resources
        try:
            openshift_resources = Resource.objects.filter(
                resource_type__name__in=["OpenShift", "OpenShift Virtualization"]
            )
        except Resource.DoesNotExist:
            openshift_resources = []

        # Find OpenStack resources
        try:
            openstack_resources = Resource.objects.filter(
                resource_type__name="OpenStack"
            )
        except Resource.DoesNotExist:
            openstack_resources = []

        # Process OpenShift resources
        for resource in openshift_resources:
            logger.info(f"Processing OpenShift resource: {resource.name}")
            if resource.get_attribute(attributes.RESOURCE_QUOTA_RESOURCES) is None:
                for quota_info in openshift_quotas:
                    self._add_quota_to_resource(resource, quota_info, apply_migration)
            else:
                logger.info(
                    f"Resource {resource.name} already has quotas defined. Skipping."
                )

        # Process OpenStack resources
        for resource in openstack_resources:
            logger.info(f"Processing OpenStack resource: {resource.name}")
            if resource.get_attribute(attributes.RESOURCE_QUOTA_RESOURCES) is None:
                for quota_info in openstack_quotas:
                    self._add_quota_to_resource(resource, quota_info, apply_migration)
            else:
                logger.info(
                    f"Resource {resource.name} already has quotas defined. Skipping."
                )

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
