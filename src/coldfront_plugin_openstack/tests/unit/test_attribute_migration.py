from unittest import mock
from os import devnull
import sys

from coldfront_plugin_openstack.tests import base
from coldfront.core.resource import models as resource_models
from coldfront.core.allocation import models as allocation_models

from django.core.management import call_command


class TestAttributeMigration(base.TestBase):

    def setUp(self) -> None:
        # Run initial setup but do not register the attributes
        backup, sys.stdout = sys.stdout, open(devnull, 'a')
        call_command('initial_setup', )
        call_command('load_test_data')
        sys.stdout = backup

    @mock.patch(
        'coldfront_plugin_openstack.management.commands.register_cloud_attributes.RESOURCE_ATTRIBUTE_MIGRATIONS',
        [
            ('Before Migration', 'After First Migration'),
            ('After First Migration', 'After Migration'),
            ('Not Present', 'Still not present'),
        ]
    )
    @mock.patch(
        'coldfront_plugin_openstack.management.commands.register_cloud_attributes.ALLOCATION_ATTRIBUTE_MIGRATIONS',
        [
            ('Before Migration', {
                'name': 'After First Migration'
            }),
            ('After First Migration', {
                'name': 'After Migration',
                'is_private': False
            }),
            ('I shall never exist', {
                'name': 'No I shall never exist'
            }),
            ('More than one', {
                'name': 'No migration'
            })
        ]
    )
    def test_rename_attribute(self):
        resource_models.ResourceAttributeType.objects.create(
            name='Before Migration',
            attribute_type=resource_models.AttributeType.objects.get(
                name='Text')
        )
        allocation_models.AllocationAttributeType.objects.create(
            name='Before Migration',
            attribute_type=allocation_models.AttributeType.objects.get(
                name='Text'),
            has_usage=False,
            is_private=True,
            is_changeable=False
        )

        call_command('register_cloud_attributes')

        resource_models.ResourceAttributeType.objects.get(
            name='After Migration'
        )
        allocation_models.AllocationAttributeType.objects.get(
            name='After Migration',
            is_private=False
        )

        with self.assertRaises(resource_models.ResourceAttributeType.DoesNotExist):
            resource_models.ResourceAttributeType.objects.get(
                name='Before Migration'
            )
            resource_models.ResourceAttributeType.objects.get(
                name='After First Migration'
            )
            resource_models.ResourceAttributeType.objects.get(
                name='Still not present'
            )

        with self.assertRaises(allocation_models.AllocationAttributeType.DoesNotExist):
            allocation_models.AllocationAttributeType.objects.get(
                name='Before Migration'
            )
            allocation_models.AllocationAttributeType.objects.get(
                name='After First Migration'
            )
            allocation_models.AllocationAttributeType.objects.get(
                name='I shall never exist'
            )

        # Test idempotency and skipping attrs with the same name
        allocation_models.AllocationAttributeType.objects.create(
            name='More than one',
            attribute_type=allocation_models.AttributeType.objects.get(
                name='Text'),
            has_usage=False,
            is_private=True,
            is_changeable=False
        )
        allocation_models.AllocationAttributeType.objects.create(
            name='More than one',
            attribute_type=allocation_models.AttributeType.objects.get(
                name='Text'),
            has_usage=False,
            is_private=False,
            is_changeable=False
        )
        call_command('register_cloud_attributes')

        with self.assertRaises(allocation_models.AllocationAttributeType.DoesNotExist):
            allocation_models.AllocationAttributeType.objects.get(
                name='No Migration'
            )
