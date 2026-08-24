"""Report total cloud quota values across active allocations."""

import csv
import json
import logging
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from coldfront.core.allocation.models import (
    Allocation,
    AllocationStatusChoice,
)
from coldfront.core.resource.models import Resource, ResourceType

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud.models.quota_models import QuotaSpecs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLOUD_TYPES = ["OpenStack", "OpenShift", "OpenShift Virtualization", "ESI"]

TOTAL_KEY = "all"


class Command(BaseCommand):
    help = "Show total cloud quotas across active allocations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cloud-type",
            choices=["all"] + CLOUD_TYPES,
            default="all",
            help="cloud type",
        )
        parser.add_argument("--project-id", help="limit scope to project id")
        parser.add_argument(
            "--per-project",
            action="store_true",
            help="report a total per project instead of a single grand total",
        )
        parser.add_argument(
            "--format", choices=["json", "csv"], default="json", help="output format"
        )

    def get_quota_names(self, resource):
        """Return the quota attribute names defined on a resource."""
        quota_specs = resource.get_attribute(attributes.RESOURCE_QUOTA_RESOURCES)
        if not quota_specs:
            logger.warning(
                f"Resource {resource.name} has no "
                f"'{attributes.RESOURCE_QUOTA_RESOURCES}' attribute, skipping. Run "
                "register_default_quotas or add_quota_to_resource to define its quotas."
            )
            return []
        return list(QuotaSpecs.model_validate(json.loads(quota_specs)).root.keys())

    def get_totals(self, cloud_type, project_id=None, per_project=False):
        try:
            resource_type = ResourceType.objects.get(name=cloud_type)
        except ObjectDoesNotExist:
            logger.info(f"Skipping {cloud_type} - resource type does not exist")
            return []

        resources = Resource.objects.filter(resource_type=resource_type)

        # Each resource defines its own quotas; merge them into one sorted column set.
        quota_names_by_resource = {r.pk: self.get_quota_names(r) for r in resources}
        all_quota_names = sorted(
            {name for names in quota_names_by_resource.values() for name in names}
        )
        if not all_quota_names:
            return []

        filter_kwargs = {}
        if project_id:
            filter_kwargs["project_id"] = project_id

        # distinct() so an allocation on two resources isn't counted twice.
        allocations = Allocation.objects.filter(
            resources__in=resources,
            status=AllocationStatusChoice.objects.get(name="Active"),
            **filter_kwargs,
        ).distinct()

        def new_group(project=None):
            return {
                "cloud_type": cloud_type,
                "project_id": project.id if project else TOTAL_KEY,
                "project_title": project.title if project else TOTAL_KEY,
                "allocations": 0,
                "quotas": {name: 0.0 for name in all_quota_names},
            }

        # Emit the total row even when it's zero.
        groups = {} if per_project else {TOTAL_KEY: new_group()}

        for allocation in allocations:
            # Only the key differs between the two modes.
            key = allocation.project_id if per_project else TOTAL_KEY
            group = groups.setdefault(
                key, new_group(allocation.project if per_project else None)
            )
            group["allocations"] += 1

            resource = allocation.resources.filter(resource_type=resource_type).first()
            for name in quota_names_by_resource.get(resource.pk, []):
                try:
                    # Values are text; unset quotas come back as None.
                    group["quotas"][name] += float(allocation.get_attribute(name))
                except (TypeError, ValueError):
                    logger.debug(
                        f"No usable value for '{name}' on allocation {allocation.id}"
                    )

        # Per-project keys are ints, the total key is a string; can't sort together.
        if per_project:
            return [groups[key] for key in sorted(groups)]
        return list(groups.values())

    def render_json(self, rows):
        self.stdout.write(json.dumps(rows, indent=4))

    def render_csv(self, rows):
        quota_names = sorted({name for row in rows for name in row["quotas"]})
        writer = csv.writer(self.stdout)
        writer.writerow(
            ["cloud_type", "project_id", "project_title", "allocations"]
            + [name.replace(" ", "_") for name in quota_names]
        )
        for row in rows:
            writer.writerow(
                [
                    row["cloud_type"],
                    row["project_id"],
                    row["project_title"],
                    row["allocations"],
                ]
                + [row["quotas"].get(name, 0.0) for name in quota_names]
            )

    def handle(self, *args, **options):
        cloud_type = options["cloud_type"]
        cloud_types = CLOUD_TYPES if cloud_type == "all" else [cloud_type]

        rows = []
        for ct in cloud_types:
            rows.extend(
                self.get_totals(
                    ct,
                    project_id=options.get("project_id"),
                    per_project=options["per_project"],
                )
            )

        if options["format"] == "json":
            self.render_json(rows)
        else:
            self.render_csv(rows)
