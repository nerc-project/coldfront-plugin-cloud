import logging
import sys

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import openstack

from novaclient import client as novaclient
from django.core.management.base import BaseCommand
from coldfront.core.resource.models import Resource, ResourceType
from coldfront.core.allocation.models import Allocation, AllocationStatusChoice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Count GPU instances."

    def add_arguments(self, parser):
        parser.add_argument(
            "--resource", type=str, required=True, help="Name of OpenStack Resource."
        )
        parser.add_argument(
            "--flavor",
            type=str,
            required=True,
            action="append",
            help="Flavor of GPU quota instances in the form <flavor name>=<quota used by 1 instance>.",
        )

    def handle(self, *args, **options):
        resource = Resource.objects.get(
            resource_type=ResourceType.objects.get(name="OpenStack"),
            name=options["resource"],
        )

        session = openstack.get_session_for_resource(resource)
        client = novaclient.Client(session=session, version=2)

        flavor_names = []
        flavor_values = []
        for flavor in options["flavor"]:
            flavor_arg = flavor.split("=")
            if len(flavor_arg) == 2:
                flavor_names.append(flavor_arg[0])
                flavor_values.append(int(flavor_arg[1]))
            else:
                flavor_names.append(flavor_arg[0])
                flavor_values.append(1)
                logger.debug(f"No GPU count specified for {flavor_arg[0]} - assuming 1")

        # Search the flavors, and construct a list of (flavor_obj, amount used by 1 instance)
        flavors = []
        for nova_flavor in client.flavors.list():
            for index, name in enumerate(flavor_names):
                if nova_flavor.name == name:
                    flavors.append((nova_flavor, flavor_values[index]))
        if len(flavors) != len(flavor_names):
            logger.critical("Not all flavor names found!")
            sys.exit(1)

        # Find all active OpenStack projects and create a
        # dictionary with the project id
        allocations = Allocation.objects.filter(
            resources__in=[resource],
            status=AllocationStatusChoice.objects.get(name="Active"),
        )
        project_id_to_allocation = {
            x.get_attribute(attributes.ALLOCATION_PROJECT_ID): x for x in allocations
        }
        count_per_project = dict()

        # There's likely less flavors than projects, so we query instances
        # by flavor.
        for flavor, value in flavors:
            gpu_servers = client.servers.list(
                search_opts={
                    "all_tenants": True,
                    "flavor": flavor.id,
                    "status": "Active",
                }
            )
            for s in gpu_servers:
                count_per_project.setdefault(s.tenant_id, 0)
                count_per_project[s.tenant_id] += value

        # Go through gpu counts and compare with quota attributes
        for project_id, active_gpu_count in count_per_project.items():
            try:
                allocation = project_id_to_allocation[project_id]
            except KeyError:
                msg = (
                    f"No active allocation found in ColdFront for project"
                    f" {project_id} containing {active_gpu_count} GPU instances."
                )
                logger.error(msg)
                continue

            allowed = allocation.get_attribute(attributes.QUOTA_GPU)
            if active_gpu_count > allowed:
                msg = (
                    f'Allocation ID {allocation.pk} of project "{allocation.project.title}"'
                    f" is using {active_gpu_count} GPU instances. (Allowed {allowed})."
                )
                logger.warning(msg)
