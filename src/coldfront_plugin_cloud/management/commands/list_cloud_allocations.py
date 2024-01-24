import sys
import csv
import json
import logging

from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import openstack
from coldfront.core.resource.models import (Resource, ResourceType)
from coldfront.core.allocation.models import (Allocation, AllocationStatusChoice)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Show cloud allocations (OpenShift and OpenStack)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cloud-type',
            choices=['all', 'OpenStack', 'OpenShift'],
            default='all',
            help='cloud type'
        )
        parser.add_argument(
            '--project-id',
            help='limit scope to project id'
        )
        parser.add_argument(
            '--format',
            choices=['json', 'csv'],
            default='json',
            help='output format'
        )

    def get_cloud_attrs(self, cloud_type):
        attrs = [
            i for i in attributes.ALLOCATION_QUOTA_ATTRIBUTES if cloud_type in i.name
        ]
        return attrs

    def get_allocations(self, cloud_type, project_id=None):
        try:
            resources = Resource.objects.filter(
                resource_type=ResourceType.objects.get(
                    name=cloud_type,
                )
            )
        except ObjectDoesNotExist as e:
            logger.error(f'{cloud_type} resource type does not exist')
            return 1

        filter_kwargs = {}

        if project_id:
            filter_kwargs['project_id'] = project_id

        allocations = Allocation.objects.filter(
            resources__in=resources,
            status=AllocationStatusChoice.objects.get(name='Active'),
            **filter_kwargs
        )

        cloud_allocations = []

        cloud_attrs = self.get_cloud_attrs(cloud_type)

        for allocation in allocations:
            alloc_info = []
            project_id = allocation.project_id
            project_title = allocation.project.title
            project_description = allocation.project.description
            pi_email = allocation.project.pi.email
            alloc_id = allocation.id
            alloc_attrs = []
            for attr in cloud_attrs:
                try:
                    alloc_attrs.append(float(allocation.get_attribute(attr.name)))
                except TypeError:
                    logger.debug(f'!!! TYPE ERROR FOR ATTR {attr} (ALLOCATION: {alloc_id})')
                    alloc_attrs.append(0)
                    continue
            alloc_info = [pi_email, cloud_type, project_id, project_title, alloc_id]
            alloc_info.extend(alloc_attrs)
            cloud_allocations.append(alloc_info)

        cloud_allocations.sort(key=lambda x: x[0:5])

        return cloud_allocations

    def render_csv(self, allocations, cloud_type):
        headers = ['pi_email', 'cloud_type', 'project_id', 'project_title', 'alloc_id']
        headers = headers + [i.name.replace(' ', '_') for i in self.get_cloud_attrs(cloud_type)]
        f = csv.writer(sys.stdout)
        allocations.insert(0, headers)
        f.writerows(allocations)

    def render_json(self, allocations):
        print(json.dumps(allocations, indent=4))

    def handle(self, *args, **options):
        fmt = options['format']
        cloud_type = options['cloud_type']
        project_id = options.get('project_id', None)

        if cloud_type == 'all' and fmt == 'csv':
            logger.error('csv output requires a single cloud type (ie not all)')
            exit(1)

        allocations = []

        if cloud_type != 'all':
            allocations = self.get_allocations(cloud_type, project_id=project_id)
        else:
            allocations = self.get_allocations('OpenStack', project_id=project_id)
            allocations.extend(self.get_allocations('OpenShift', project_id=project_id))

        if fmt == 'json':
            self.render_json(allocations)
        elif fmt == 'csv':
            self.render_csv(allocations, cloud_type)
