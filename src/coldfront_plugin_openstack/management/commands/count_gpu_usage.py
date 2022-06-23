import logging
import sys

from coldfront_plugin_openstack import attributes
from coldfront_plugin_openstack import openstack

from novaclient import client as novaclient
from django.core.management.base import BaseCommand
from coldfront.core.resource.models import (Resource,
                                            ResourceType)
from coldfront.core.allocation.models import (Allocation,
                                              AllocationStatusChoice)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Count GPU instances.'

    def add_arguments(self, parser):
        parser.add_argument('--flavor', type=str, required=True,
                            help='Flavor of GPU quota instances.')

    def handle(self, *args, **options):
        resources = Resource.objects.filter(
            resource_type=ResourceType.objects.get(name='OpenStack')
        )
        for resource in resources:
            session = openstack.get_session_for_resource()
            client = novaclient.Client(session=session, version=2)

            # Find the flavor from the name
            flavor = None
            for f in client.flavors.list():
                if f.name == options['flavor']:
                    flavor = f
            if not flavor:
                logger.critical(f'Flavor {options["flavor"]} does not exist.')
                sys.exit(1)

            # Query listing of gpu servers and aggregate by project
            gpu_servers = client.servers.list(search_opts={
                'all_tenants': True,
                'flavor': flavor.id,
                'status': 'Active',
            })
            count_per_project = dict()
            for s in gpu_servers:
                count_per_project.setdefault(s.tenant_id, 0)
                count_per_project[s.tenant_id] += 1

            # Find all active OpenStack projects and create a
            # dictionary with the project id
            allocations = Allocation.objects.filter(
                resources__in=resource,
                status=AllocationStatusChoice.objects.get(name='Active')
            )
            project_id_to_allocation = {
                x.get_attribute(attributes.ALLOCATION_PROJECT_ID): x
                for x in allocations
            }

            # Go through gpu counts and compare with quota attributes
            for project_id, active_gpu_count in count_per_project.items():
                try:
                    allocation = project_id_to_allocation[project_id]
                except KeyError:
                    msg = (f'No active allocation found in ColdFront for project'
                           f' {project_id} containing {active_gpu_count} GPU instances.')
                    logger.error(msg)
                    continue

                allowed = allocation.get_attribute(attributes.QUOTA_GPU)
                if active_gpu_count > allowed:
                    msg = (f'{allocation.pk} of project "{allocation.project.title}"'
                           f' is using {active_gpu_count} GPU instances. (Allowed {allowed}.')
                    logger.warning(msg)
