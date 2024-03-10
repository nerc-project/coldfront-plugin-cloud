from django.core.management.base import BaseCommand
from django.core.management import call_command

from coldfront.core.resource.models import (Resource,
                                            ResourceAttribute,
                                            ResourceAttributeType,
                                            ResourceType)

from coldfront_plugin_cloud import attributes


class Command(BaseCommand):
    help = 'Create ESI resource'
    # (Quan Pham) TODO Know what other attributes an ESI resource must/could have
    # That could be set from cli, or through other means

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, required=True,
                            help='Name of ESI resource')
        parser.add_argument('--auth-url', type=str, required=True,
                            help='URL of the ESI esi Identity Endpoint')
        parser.add_argument('--users-domain', type=str, default='default',
                            help='Domain ID to create users')
        parser.add_argument('--projects-domain', type=str, default='default',
                            help='Domain ID to create projects')
        parser.add_argument('--idp', type=str, required=True,
                            help='Identity provider configured in ESI cluster')
        parser.add_argument('--protocol', type=str, default='openid',
                            help='Federation protocol (default: openid)')
        parser.add_argument('--role', type=str, default='member',
                            help='Role for user when added to project (default: member)')
        parser.add_argument('--public-network', type=str, default='',
                            help='Public network ID for default networks. '
                                 'If not specified, no default network is '
                                 'created for new projects.')
        parser.add_argument('--network-cidr', type=str, default='192.168.0.0/24',
                            help='CIDR for default networks. '
                                 'Ignored if no --public-network.')

    def handle(self, *args, **options):
        esi, _ = Resource.objects.get_or_create(
            resource_type=ResourceType.objects.get(name='ESI'),
            parent_resource=None,
            name=options['name'],
            description='ESI Bare Metal environment',
            is_available=True,
            is_public=True,
            is_allocatable=True
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_AUTH_URL),
            resource=esi,
            value=options['auth_url']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_PROJECT_DOMAIN),
            resource=esi,
            value=options['projects_domain']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_USER_DOMAIN),
            resource=esi,
            value=options['users_domain']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_IDP),
            resource=esi,
            value=options['idp']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_FEDERATION_PROTOCOL),
            resource=esi,
            value=options['protocol']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_ROLE),
            resource=esi,
            value=options['role']
        )

        if options['public_network']:
            ResourceAttribute.objects.get_or_create(
                resource_attribute_type=ResourceAttributeType.objects.get(
                    name=attributes.RESOURCE_DEFAULT_PUBLIC_NETWORK),
                resource=esi,
                value=options['public_network']
            )
            ResourceAttribute.objects.get_or_create(
                resource_attribute_type=ResourceAttributeType.objects.get(
                    name=attributes.RESOURCE_DEFAULT_NETWORK_CIDR),
                resource=esi,
                value=options['network_cidr']
            )
