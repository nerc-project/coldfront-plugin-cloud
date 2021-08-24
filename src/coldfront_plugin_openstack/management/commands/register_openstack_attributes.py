from django.core.management.base import BaseCommand
from django.core.management import call_command

from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models


class Command(BaseCommand):
    help = 'Add default OpenStack allocation related choices'

    def register_allocation_attributes(self):
        for name, attribute_type, has_usage, is_private in (
                ('OpenStack Compute Instance Quota', 'Int', False, False),
                ('OpenStack Compute RAM Quota', 'Int', False, False),
                ('OpenStack Compute vCPU Quota', 'Int', False, False),
                ('OpenStack Project ID', 'Text', False, False),
                ('OpenStack Project Name', 'Text', False, False),
        ):
            allocation_models.AllocationAttributeType.objects.get_or_create(
                name=name,
                attribute_type=allocation_models.AttributeType.objects.get(
                    name=attribute_type),
                has_usage=has_usage,
                is_private=is_private
            )

    def register_resource_attributes(self):
        for resource_attribute_type, attribute_type in (
            ('OpenStack Auth URL', 'Text'),
            ('OpenStack Domain for Projects', 'Text'),
            ('OpenStack Domain for Users', 'Text'),
            ('OpenStack Federation Protocol', 'Text'),
            ('OpenStack Identity Provider', 'Text'),
            ('OpenStack Role for User in Project', 'Text'),
        ):
            resource_models.ResourceAttributeType.objects.get_or_create(
                name=resource_attribute_type,
                attribute_type=resource_models.AttributeType.objects.get(
                    name=attribute_type)
            )

    def register_resource_type(self):
        resource_models.ResourceType.objects.get_or_create(
            name='OpenStack', description='OpenStack Cloud')

    def handle(self, *args, **options):
        self.register_resource_type()
        self.register_resource_attributes()
        self.register_allocation_attributes()
