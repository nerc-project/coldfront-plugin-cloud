import json
import logging

from django.core.management.base import BaseCommand
from coldfront.core.resource.models import (
    Resource,
    ResourceAttribute,
    ResourceAttributeType,
)
from coldfront.core.allocation.models import AllocationAttributeType, AttributeType

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud.models.quota_models import QuotaSpecs, QuotaSpec

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--display-name",
            type=str,
            required=True,
            help="The display name for the quota attribute to add to the resource type.",
        )
        parser.add_argument(
            "--resource-name",
            type=str,
            required=True,
            help="The name of the resource to add the storage attribute to.",
        )
        parser.add_argument(
            "--quota-label",
            type=str,
            required=True,
            help="The cluster-side label for the quota.",
        )
        parser.add_argument(
            "--multiplier",
            type=int,
            default=0,
            help="Multiplier applied per SU quantity (int).",
        )
        parser.add_argument(
            "--static-quota",
            type=int,
            default=0,
            help="Static quota added to every SU quantity (int).",
        )
        parser.add_argument(
            "--unit-suffix",
            type=str,
            default="",
            help='Unit suffix to append to formatted quota values (e.g. "Gi").',
        )
        parser.add_argument(
            "--resource-type",
            type=str,
            default="",
            help="Indicates which resource type this quota is. Type `storage` is relevant for storage billing",
        )
        parser.add_argument(
            "--invoice-name",
            type=str,
            default="",
            help="Name of quota as it appears on invoice. Required if --resource-type is set to `storage`.",
        )

    def handle(self, *args, **options):
        if options["resource_type"] == "storage" and not options["invoice_name"]:
            logger.error(
                "--invoice-name must be provided when reousrce type is `storage`."
            )

        resource_name = options["resource_name"]
        display_name = options["display_name"]
        new_quota_spec = QuotaSpec(**options)
        new_quota_dict = {display_name: new_quota_spec.model_dump()}
        QuotaSpecs.model_validate(new_quota_dict)

        resource = Resource.objects.get(name=resource_name)
        available_quotas_attr, created = ResourceAttribute.objects.get_or_create(
            resource=resource,
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_QUOTA_RESOURCES
            ),
            defaults={"value": json.dumps(new_quota_dict)},
        )

        # TODO (Quan): Dict update allows migration of existing quotas. This is fine?
        if not created:
            available_quotas_dict = json.loads(available_quotas_attr.value)
            available_quotas_dict.update(new_quota_dict)
            QuotaSpecs.model_validate(available_quotas_dict)  # Validate uniqueness
            available_quotas_attr.value = json.dumps(available_quotas_dict)
            available_quotas_attr.save()

        # Now create Allocation Attribute for this quota
        AllocationAttributeType.objects.get_or_create(
            name=display_name,
            defaults={
                "attribute_type": AttributeType.objects.get(name="Int"),
                "has_usage": False,
                "is_private": False,
                "is_changeable": True,
            },
        )

        logger.info("Added quota '%s' to resource '%s'.", display_name, resource_name)
