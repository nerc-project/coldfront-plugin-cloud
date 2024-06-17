from django.core.management.base import BaseCommand
from django.core.management import call_command

from coldfront.core.resource.models import (Resource,
                                            ResourceAttribute,
                                            ResourceAttributeType,
                                            ResourceType)

from coldfront_plugin_cloud import attributes


class Command(BaseCommand):
    help = 'Create OpenShift resource'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, required=True,
                            help='Name of OpenShift resource')
        parser.add_argument('--cluster-url', type=str, required=True,
                            help='URL of the Openshift cluster')
        parser.add_argument('--identity-name', type=str, required=True,
                            help='Name of the cluster\'s identity provider')
        parser.add_argument('--role', type=str, default='edit',
                            help='Role for user when added to project (default: edit)')

    def handle(self, *args, **options):
        openshift, _ = Resource.objects.get_or_create(
            resource_type=ResourceType.objects.get(name='OpenShift'),
            parent_resource=None,
            name=options['name'],
            description='OpenShift cloud environment',
            is_available=True,
            is_public=True,
            is_allocatable=True
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_AUTH_URL),
            resource=openshift,
            value=options['cluster_url']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_ROLE),
            resource=openshift,
            value=options['role']
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_IDENTITY_NAME),
            resource=openshift,
            value=options['identity_name']
        )
        
