import requests

from django.core.management.base import BaseCommand

from coldfront.core.resource.models import (
    Resource,
    ResourceAttribute,
    ResourceAttributeType,
    ResourceType,
)

from coldfront_plugin_cloud import attributes

TARGET_ATTRIBUTE = "eula"


class Command(BaseCommand):
    help = "Update EULA from EULA URL"

    def add_arguments(self, parser):
        parser.add_argument(
            "--resource_name", type=str, required=True, help="Name of Resource"
        )

    def handle(self, *args, **options):

        try:
            resource_obj = Resource.objects.get(name=options["resource_name"])
        except Resource.DoesNotExist:
            raise CommandError("Resource does not exist")

        eula_url = resource_obj.get_attribute(attributes.RESOURCE_EULA_URL)

        if eula_url is None:
            raise CommandError("Attribute EULA_URL is not set")

        response = requests.get(eula_url)

        if not response:
            raise CommandError("Failed to get the EULA from the provided URL")

        try:
            resource_attribute_obj = ResourceAttribute.objects.get(
                resource_attribute_type=ResourceAttributeType.objects.get(
                    name=TARGET_ATTRIBUTE
                ),
                resource=resource_obj,
            )
            resource_attribute_obj.value = response.text
            resource_attribute_obj.save()
        except ResourceAttribute.DoesNotExist:
            ResourceAttribute.objects.create(
                resource_attribute_type=ResourceAttributeType.objects.get(
                    name=TARGET_ATTRIBUTE
                ),
                resource=resource_obj,
                value=response.text,
            )
