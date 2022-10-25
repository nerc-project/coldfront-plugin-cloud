import requests

from django.core.management.base import BaseCommand

from coldfront.core.resource.models import (
    Resource,
    ResourceAttribute,
    ResourceAttributeType,
    ResourceType,
)

from coldfront_plugin_cloud import attributes

EULA = "eula"


class Command(BaseCommand):
    help = "Update EULA from EULA URL"

    def add_arguments(self, parser):
        parser.add_argument(
            "--resource_name", type=str, required=True, help="Name of Resource"
        )
        parser.add_argument(
            "--resource_type", type=str, required=True, help="Type of Resource"
        )

    def handle(self, *args, **options):

        resource_obj = Resource.objects.get(
            resource_type=ResourceType.objects.get(name=options["resource_type"]),
            name=options["resource_name"],
        )

        eula_url = resource_obj.get_attribute(attributes.RESOURCE_EULA_URL)
        response = requests.get(eula_url)

        try:
            resource_attribute_obj = ResourceAttribute.objects.get(
                resource_attribute_type=ResourceAttributeType.objects.get(name=EULA),
                resource=resource_obj,
            )
            resource_attribute_obj.value = response.text
            resource_attribute_obj.save()
        except ResourceAttribute.DoesNotExist:
            ResourceAttribute.objects.create(
                resource_attribute_type=ResourceAttributeType.objects.get(name=EULA),
                resource=resource_obj,
                value=response.text,
            )

        print(resource_obj.get_attribute(EULA))
