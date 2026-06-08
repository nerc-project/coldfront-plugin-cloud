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
    help = 'Show cloud quotas (OpenShift and OpenStack)'

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
            choices=['json'],
            default='json',
            help='output format'
        )

    def get_cloud_attrs(self, cloud_type):
        attrs = [
            i for i in attributes.ALLOCATION_QUOTA_ATTRIBUTES if cloud_type in i
        ]
        return attrs

    def get_quota_totals(self, cloud_type, project_id=None):
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

        totals = {}

        for attr in attributes.ALLOCATION_QUOTA_ATTRIBUTES:
            if cloud_type in attr:
                total = 0
                for allocation in allocations:
                    try:
                        val = float(allocation.get_attribute(attr))
                        total += val
                    except TypeError:
                        continue
                totals[attr] = total
        return totals

    def render_json(self, quota_totals):
        print(json.dumps(quota_totals, indent=4))

    def handle(self, *args, **options):
        fmt = options['format']
        cloud_type = options['cloud_type']
        project_id = options.get('project_id', None)

        if cloud_type != 'all':
            quota_totals = self.get_quota_totals(cloud_type, project_id=project_id)
        else:
            quota_totals = self.get_quota_totals('OpenStack', project_id=project_id)
            quota_totals.update(self.get_quota_totals('OpenShift', project_id=project_id))

        if fmt == 'json':
            self.render_json(quota_totals)
