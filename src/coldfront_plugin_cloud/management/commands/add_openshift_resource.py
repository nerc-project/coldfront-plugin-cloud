from django.core.management.base import BaseCommand
from django.core.management import call_command

from coldfront.core.resource.models import (
    Resource,
    ResourceAttribute,
    ResourceAttributeType,
    ResourceType,
)

from coldfront_plugin_cloud import attributes, openshift


class Command(BaseCommand):
    help = "Create OpenShift resource"

    @staticmethod
    def validate_role(role):
        if role not in openshift.OPENSHIFT_ROLES:
            raise ValueError(
                f"Invalid role, {role} is not one of {', '.join(openshift.OPENSHIFT_ROLES)}"
            )

    def add_arguments(self, parser):
        parser.add_argument(
            "--name", type=str, required=True, help="Name of OpenShift resource"
        )
        parser.add_argument(
            "--internal-name",
            type=str,
            required=False,
            help="Internal name of cluster used for invoicing. Defaults to public name",
        )
        parser.add_argument(
            "--api-url",
            type=str,
            required=True,
            help="API URL of the OpenShift cluster",
        )
        parser.add_argument(
            "--idp", type=str, required=True, help="Name of Openshift identity provider"
        )
        parser.add_argument(
            "--role",
            type=str,
            default="edit",
            help="Role for user when added to project (default: edit)",
        )
        parser.add_argument(
            "--for-virtualization",
            action="store_true",
            help="Indicates this is an OpenShift Virtualization resource (default: False)",
        )

    def handle(self, *args, **options):
        self.validate_role(options["role"])

        if options["for_virtualization"]:
            resource_description = "OpenShift Virtualization environment"
            resource_type = "OpenShift Virtualization"
        else:
            resource_description = "OpenShift cloud environment"
            resource_type = "OpenShift"

        openshift, _ = Resource.objects.get_or_create(
            resource_type=ResourceType.objects.get(name=resource_type),
            parent_resource=None,
            name=options["name"],
            description=resource_description,
            is_available=True,
            is_public=True,
            is_allocatable=True,
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_API_URL
            ),
            resource=openshift,
            value=options["api_url"],
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_IDENTITY_NAME
            ),
            resource=openshift,
            value=options["idp"],
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_ROLE
            ),
            resource=openshift,
            value=options["role"],
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_CLUSTER_NAME
            ),
            resource=openshift,
            value=options["internal_name"]
            if options["internal_name"]
            else options["name"],
        )

        # Add common Openshift resources (cpu, memory, etc)
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_LIMITS_CPU,
            resource_name=options["name"],
            quota_label="limits.cpu",
            multiplier=1,
        )
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_LIMITS_MEMORY,
            resource_name=options["name"],
            quota_label="limits.memory",
            multiplier=4096,
            unit_suffix="Mi",
        )
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            resource_name=options["name"],
            quota_label="limits.ephemeral-storage",
            multiplier=5,
            unit_suffix="Gi",
        )
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_PVC,
            resource_name=options["name"],
            quota_label="persistentvolumeclaims",
            multiplier=2,
        )
