import logging
import re

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import openstack
from coldfront_plugin_cloud import openshift
from coldfront_plugin_cloud import esi
from coldfront_plugin_cloud import utils
from coldfront_plugin_cloud import tasks

from django.core.management.base import BaseCommand, CommandError
from coldfront.core.resource.models import (Resource,
                                            ResourceType)
from coldfront.core.allocation.models import (Allocation,
                                              AllocationStatusChoice,
                                              AllocationUser)
from keystoneauth1.exceptions import http


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Validates quotas and users in resource allocations.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Apply expected state if validation fails.')

    @staticmethod
    def sync_users(project_id, allocation, allocator, apply):
        coldfront_users = AllocationUser.objects.filter(allocation=allocation, status__name='Active')
        allocation_users = allocator.get_users(project_id)
        failed_validation = False

        # Create users that exist in coldfront but not in the resource
        for coldfront_user in coldfront_users:
            if coldfront_user.user.username not in allocation_users:
                failed_validation = True
                logger.warn(f"{coldfront_user.user.username} is not part of {project_id}")
                if apply:
                    tasks.add_user_to_allocation(coldfront_user.pk)

        # remove users that are in the resource but not in coldfront
        users = set([coldfront_user.user.username for coldfront_user in coldfront_users])
        for allocation_user in allocation_users:
            if allocation_user not in users:
                failed_validation = True
                logger.warn(f"{allocation_user} exists in the resource {project_id} but not in coldfront")
                if apply:
                    allocator.remove_role_from_user(allocation_user, project_id)

        return failed_validation

    def check_institution_specific_code(self, allocation, apply):
        attr = attributes.ALLOCATION_INSTITUTION_SPECIFIC_CODE
        isc = allocation.get_attribute(attr)
        if not isc:
            alloc_str = f'{allocation.pk} of project "{allocation.project.title}"'
            msg = f'Attribute "{attr}" missing on allocation {alloc_str}'
            logger.warn(msg)
            if apply:
                utils.set_attribute_on_allocation(
                    allocation, attr, "N/A"
                )
                logger.warn(f'Attribute "{attr}" added to allocation {alloc_str}')

    def handle(self, *args, **options):

        # Deal with Openstack and ESI resources
        openstack_resources = Resource.objects.filter(
            resource_type__name__in=['OpenStack', 'ESI']
        )
        openstack_allocations = Allocation.objects.filter(
            resources__in=openstack_resources,
            status=AllocationStatusChoice.objects.get(name='Active')
        )
        for allocation in openstack_allocations:
            self.check_institution_specific_code(allocation, options["apply"])
            allocation_str = f'{allocation.pk} of project "{allocation.project.title}"'
            msg = f'Starting resource validation for allocation {allocation_str}.'
            logger.debug(msg)

            failed_validation = False

            allocator = tasks.find_allocator(allocation)

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

            failed_validation = Command.sync_users(project_id, allocation, allocator, options["apply"])

            obj_key = openstack.OpenStackResourceAllocator.QUOTA_KEY_MAPPING['object']['keys'][attributes.QUOTA_OBJECT_GB]

            for attr in tasks.get_expected_attributes(allocator):
                key = allocator.QUOTA_KEY_MAPPING_ALL_KEYS.get(attr, None)
                if not key:
                    # Note(knikolla): Some attributes are only maintained
                    # for bookkeeping purposes and do not have a
                    # corresponding quota set on the service.
                    continue

                expected_value = allocation.get_attribute(attr)
                current_value = quota.get(key, None)
                if key == obj_key and expected_value <= 0:
                    expected_obj_value = 1
                    current_value = int(allocator.object(project_id).head_account().get(obj_key))
                    if current_value != expected_obj_value:
                        failed_validation = True
                        msg = (f'Value for quota for {attr} = {current_value} does not match expected'
                                f' value of {expected_obj_value} on allocation {allocation_str}')
                        logger.warning(msg)
                elif expected_value is None and current_value:
                    msg = (f'Attribute "{attr}" expected on allocation {allocation_str} but not set.'
                            f' Current quota is {current_value}.')
                    if options['apply']:
                        utils.set_attribute_on_allocation(
                            allocation, attr, current_value
                        )
                        msg = f'{msg} Attribute set to match current quota.'
                    logger.warning(msg)
                elif not current_value == expected_value:
                    failed_validation = True
                    msg = (f'Value for quota for {attr} = {current_value} does not match expected'
                            f' value of {expected_value} on allocation {allocation_str}')
                    logger.warning(msg)

            if failed_validation and options['apply']:
                try:
                    allocator.set_quota(
                        allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
                    )
                except Exception as e:
                    logger.error(f'setting {allocation.resources.first()} quota failed: {e}')
                    continue
                logger.warning(f'Quota for allocation {allocation_str} was out of date. Reapplied!')

        # Deal with OpenShift and Openshift VM

        openshift_resources = Resource.objects.filter(
            resource_type__name__in=['OpenShift', 'Openshift Virtualization']
        )
        openshift_allocations = Allocation.objects.filter(
            resources__in=openshift_resources,
            status=AllocationStatusChoice.objects.get(name="Active"),
        )

        for allocation in openshift_allocations:
            self.check_institution_specific_code(allocation, options["apply"])
            allocation_str = f'{allocation.pk} of project "{allocation.project.title}"'
            logger.debug(
                f"Starting resource validation for allocation {allocation_str}."
            )

            allocator = tasks.find_allocator(allocation)

            project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

            if not project_id:
                logger.error(f"{allocation_str} is active but has no Project ID set.")
                continue

            try:
                allocator._get_project(project_id)
            except http.NotFound:
                logger.error(
                    f"{allocation_str} has Project ID {project_id}. But"
                    f" no project found in OpenShift."
                )
                continue

            quota = allocator.get_quota(project_id)

            failed_validation = Command.sync_users(project_id, allocation, allocator, options["apply"])

            for attr in tasks.get_expected_attributes(allocator):
                key_with_lambda = allocator.QUOTA_KEY_MAPPING.get(attr, None)

                # This gives me just the plain key
                key = list(key_with_lambda(1).keys())[0]

                expected_value = allocation.get_attribute(attr)
                current_value = quota.get(key, None)

                PATTERN = r"([0-9]+)(m|Ki|Mi|Gi|Ti|Pi|Ei|K|M|G|T|P|E)?"

                suffix = {
                    "Ki": 2**10,
                    "Mi": 2**20,
                    "Gi": 2**30,
                    "Ti": 2**40,
                    "Pi": 2**50,
                    "Ei": 2**60,
                    "m": 10**-3,
                    "K": 10**3,
                    "M": 10**6,
                    "G": 10**9,
                    "T": 10**12,
                    "P": 10**15,
                    "E": 10**18,
                }

                if current_value and current_value != "0":
                    result = re.search(PATTERN, current_value)

                    if result is None:
                        raise CommandError(
                            f"Unable to parse current_value = '{current_value}' for {attr}"
                        )

                    value = int(result.groups()[0])
                    unit = result.groups()[1]

                    # Convert to number i.e. without any unit suffix

                    if unit is not None:
                        current_value = value * suffix[unit]
                    else:
                        current_value = value

                    # Convert some attributes to units that coldfront uses

                    if "RAM" in attr:
                        current_value = round(current_value / suffix["Mi"])
                    elif "Storage" in attr:
                        current_value = round(current_value / suffix["Gi"])
                elif current_value and current_value == "0":
                    current_value = 0

                if expected_value is None and current_value is not None:
                    msg = (
                        f'Attribute "{attr}" expected on allocation {allocation_str} but not set.'
                        f" Current quota is {current_value}."
                    )
                    if options["apply"]:
                        utils.set_attribute_on_allocation(
                            allocation, attr, current_value
                        )
                        msg = f"{msg} Attribute set to match current quota."
                    logger.warning(msg)
                elif not (current_value == expected_value):
                    msg = (
                        f"Value for quota for {attr} = {current_value} does not match expected"
                        f" value of {expected_value} on allocation {allocation_str}"
                    )
                    logger.warning(msg)

                    if options["apply"]:
                        try:
                            allocator.set_quota(project_id)
                            logger.warning(
                                f"Quota for allocation {project_id} was out of date. Reapplied!"
                            )
                        except Exception as e:
                            logger.error(f'setting openshift quota failed: {e}')
                            continue
