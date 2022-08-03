import logging

from coldfront_plugin_openstack import attributes
from coldfront_plugin_openstack import openstack

from django.core.management.base import BaseCommand
from coldfront.core.resource.models import (Resource,
                                            ResourceType)
from coldfront.core.allocation.models import (Allocation,
                                              AllocationStatusChoice)
from keystoneauth1.exceptions import http


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Validates quotas and users in resource allocations.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Apply expected state if validation fails.')

    def handle(self, *args, **options):
        supported_resources = Resource.objects.filter(
            resource_type=ResourceType.objects.get(
                name='OpenStack'
            )
        )
        allocations = Allocation.objects.filter(
            resources__in=supported_resources,
            status=AllocationStatusChoice.objects.get(name='Active')
        )
        for allocation in allocations:
            allocation_str = f'{allocation.pk} of project "{allocation.project.title}"'
            msg = f'Starting resource validation for allocation {allocation_str}.'
            logger.debug(msg)

            failed_validation = False

            allocator = openstack.OpenStackResourceAllocator(
                allocation.resources.first(),
                allocation
            )

            project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
            if not project_id:
                logger.error(f'{allocation_str} is active but has no Project ID set.')
                continue

            try:
                allocator.identity.projects.get(project_id)
            except http.NotFound:
                logger.error(f'{allocation_str} has Project ID {project_id}. But'
                             f' no project found in OpenStack.')
                continue

            quota = allocator.get_quota(project_id)
            for attr in attributes.ALLOCATION_QUOTA_ATTRIBUTES:
                if 'OpenStack' in attr:
                    expected_value = allocation.get_attribute(attr)
                    if expected_value is None:
                        msg = f'Attribute "{attr}" expected on allocation {allocation_str} but not set.'
                        logger.warning(msg)
                    else:
                        key = openstack.QUOTA_KEY_MAPPING_ALL_KEYS.get(attr, None)
                        if not key:
                            # Note(knikolla): Some attributes are only maintained
                            # for bookkeeping purposes and do not have a
                            # corresponding quota set on the service.
                            continue
                        elif not (value := quota.get(key, None)) == expected_value:
                            failed_validation = True
                            msg = (f'Value for quota for {attr} = {value} does not match expected'
                                   f' value of {expected_value} on allocation {allocation_str}')
                            logger.warning(msg)

            if failed_validation and options['apply']:
                allocator.set_quota(
                    allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
                )
                logger.warning(f'Quota for allocation {allocation_str} was out of date. Reapplied!')
