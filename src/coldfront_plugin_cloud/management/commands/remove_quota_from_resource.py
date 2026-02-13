import json
import logging
from django.core.management.base import BaseCommand

from coldfront.core.resource.models import (
    Resource,
    ResourceAttribute,
    ResourceAttributeType,
)
from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud.models.quota_models import QuotaSpecs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Remove a quota from a resource's available resource quotas. This does not remove the quota's allocation attributes, so prior allocations will still see this quota. Use --apply to perform the change."

    def add_arguments(self, parser):
        parser.add_argument(
            "--resource-name",
            type=str,
            help="Name of the Resource to modify.",
        )
        parser.add_argument(
            "--display-name",
            type=str,
            help="Display name of the quota to remove.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            dest="apply",
            help="If set, apply the removal",
        )

    def handle(self, *args, **options):
        resource_name = options["resource_name"]
        display_name = options["display_name"]
        apply_change = options["apply"]

        resource = Resource.objects.get(name=resource_name)
        rat = ResourceAttributeType.objects.get(
            name=attributes.RESOURCE_QUOTA_RESOURCES
        )
        available_attr = ResourceAttribute.objects.get(
            resource=resource, resource_attribute_type=rat
        )

        available_dict = json.loads(available_attr.value or "{}")

        if display_name not in available_dict:
            logger.info(
                "Display name '%s' not present on resource '%s'. Nothing to remove.",
                display_name,
                resource_name,
            )
            return

        logger.info(
            "Removing quota '%s' from resource '%s':", display_name, resource_name
        )
        if not apply_change:
            return

        del available_dict[display_name]
        QuotaSpecs.model_validate(available_dict)
        available_attr.value = json.dumps(available_dict)
        available_attr.save()
