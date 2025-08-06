from django.core.management.base import BaseCommand

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
        parser.add_argument(
            "--ibm-storage-available",
            action="store_true",
            help="Indicates that Ibm Scale storage is available in this resource (default: False)",
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
                name=attributes.RESOURCE_IBM_AVAILABLE
            ),
            resource=openshift,
            value="true" if options["ibm_storage_available"] else "false",
        )
