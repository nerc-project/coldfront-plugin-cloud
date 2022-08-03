import logging

from django.core.management.base import BaseCommand

from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models

from coldfront_plugin_cloud import attributes

logger = logging.getLogger(__name__)


ALLOCATION_ATTRIBUTE_MIGRATIONS = [
    ('Example old attribute name', {
        'name': 'Example new attribute name',
        'is_private': False,
        'is_changeable': False,
    }),
]

RESOURCE_ATTRIBUTE_MIGRATIONS = [
    ('Example old attribute name', 'Example new attribute name'),
]


class Command(BaseCommand):
    help = 'Add attributes for OpenStack and OpenShift resources/allocations'

    def migrate_allocation_attributes(self):
        for old_name, new_dict in ALLOCATION_ATTRIBUTE_MIGRATIONS:
            logger.debug(f'Looking for outdated allocation attribute "{old_name}".')
            try:
                attr = allocation_models.AllocationAttributeType.objects.get(
                    name=old_name,
                )
                attr.name = new_dict['name']
                if 'is_private' in new_dict:
                    attr.is_private = new_dict['is_private']
                if 'is_changeable' in new_dict:
                    attr.is_changeable = new_dict['is_changeable']
                attr.save()
                logger.info(f'Allocation attribute "{old_name}" migrated to "{new_dict}".')
            except allocation_models.AllocationAttributeType.DoesNotExist:
                logger.debug(f'Outdated allocation attribute "{old_name}" not found.')
            except allocation_models.AllocationAttributeType.MultipleObjectsReturned:
                logger.error(f'Multiple allocation attributes with name "{old_name}".'
                             f' Cannot perform automatic migration.')

    def migrate_resource_attributes(self):
        for old_name, new_name in RESOURCE_ATTRIBUTE_MIGRATIONS:
            logger.debug(f'Looking for outdated resource attribute "{old_name}".')
            try:
                attr = resource_models.ResourceAttributeType.objects.get(
                    name=old_name,
                )
                attr.name = new_name
                attr.save()
                logger.info(f'Resource attribute "{old_name}" migrated to "{new_name}".')
            except resource_models.ResourceAttributeType.DoesNotExist:
                logger.debug(f'Outdated resource attribute "{old_name}" not found.')
            except resource_models.ResourceAttributeType.MultipleObjectsReturned:
                logger.error(f'Multiple resource attributes with name "{old_name}".'
                             f' Cannot perform automatic migration.')

    def register_allocation_attributes(self):
        def register(attribute_name, attribute_type):
            allocation_models.AllocationAttributeType.objects.get_or_create(
                name=attribute_name,
                attribute_type=allocation_models.AttributeType.objects.get(
                    name=attribute_type),
                has_usage=False,
                is_private=False,
                is_changeable='Quota' in attribute_name
            )

        for allocation_attribute in attributes.ALLOCATION_ATTRIBUTES:
            register(allocation_attribute, 'Text')

        for allocation_quota_attribute in attributes.ALLOCATION_QUOTA_ATTRIBUTES:
            register(allocation_quota_attribute, 'Int')

    def register_resource_attributes(self):
        for resource_attribute_type in attributes.RESOURCE_ATTRIBUTES:
            resource_models.ResourceAttributeType.objects.get_or_create(
                name=resource_attribute_type,
                attribute_type=resource_models.AttributeType.objects.get(
                    name='Text')
            )

    def register_resource_type(self):
        resource_models.ResourceType.objects.get_or_create(
            name='OpenStack', description='OpenStack Cloud'
        )
        resource_models.ResourceType.objects.get_or_create(
            name='OpenShift', description='OpenShift Cloud'
        )

    def handle(self, *args, **options):
        self.register_resource_type()
        self.migrate_resource_attributes()
        self.migrate_allocation_attributes()
        self.register_resource_attributes()
        self.register_allocation_attributes()
