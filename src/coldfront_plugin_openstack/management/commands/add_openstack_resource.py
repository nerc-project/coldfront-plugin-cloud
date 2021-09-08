from django.core.management.base import BaseCommand
from django.core.management import call_command

from coldfront.core.resource.models import (Resource,
                                            ResourceAttribute,
                                            ResourceAttributeType,
                                            ResourceType)


class Command(BaseCommand):
    help = 'Create OpenStack resource'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, required=True,
                            help='Name of OpenStack resource')
        parser.add_argument('--auth-url', type=str, required=True,
                            help='URL of the OpenStack Identity Endpoint')
        parser.add_argument('--users-domain', type=str, default='default',
                            help='Domain ID to create users')
        parser.add_argument('--projects-domain', type=str, default='default',
                            help='Domain ID to create projects')
        parser.add_argument('--idp', type=str, required=True,
                            help='Identity provider configured in OpenStack')
        parser.add_argument('--protocol', type=str, default='openid',
                            help='Federation protocol (default: openid)')
        parser.add_argument('--role', type=str, default='member',
                            help='Role for user when added to project (default: member)')

    def handle(self, *args, **options):
        openstack = Resource.objects.get_or_create(
            resource_type=ResourceType.objects.get(name='OpenStack'),
            parent_resource=None,
            name=options['name'],
            description='OpenStack test cloud environment',
            is_available=True,
            is_public=True,
            is_allocatable=True
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name='OpenStack Auth URL'),
            resource=openstack,
            value=options['auth-url']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name='OpenStack Domain for Projects'),
            resource=openstack,
            value=options['projects-domain']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name='OpenStack Domain for Users'),
            resource=openstack,
            value=options['users-domain']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name='OpenStack Identity Provider'),
            resource=openstack,
            value=options['idp']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name='OpenStack Federation Protocol'),
            resource=openstack,
            value=options['protocol']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name='OpenStack Role for User in Project'),
            resource=openstack,
            value=options['role']
        )
