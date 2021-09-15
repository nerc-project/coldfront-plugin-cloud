import uuid

from django.test import TestCase

from coldfront.core.allocation.models import (Allocation,
                                              AllocationStatusChoice,
                                              AllocationUser,
                                              AllocationUserStatusChoice)

from django.contrib.auth.models import User
from coldfront.core.project.models import (Project,
                                           ProjectUser,
                                           ProjectUserRoleChoice,
                                           ProjectUserStatusChoice, ProjectStatusChoice)
from coldfront.core.resource.models import (Resource,
                                            ResourceType,
                                            ResourceAttribute,
                                            ResourceAttributeType)
from django.core.management import call_command

from coldfront_plugin_openstack import attributes


class TestBase(TestCase):

    def setUp(self) -> None:
        call_command('initial_setup')
        call_command('load_test_data')
        call_command('register_openstack_attributes')

    @staticmethod
    def new_user(username=None) -> User:
        username = username or f'{uuid.uuid4().hex}@example.com'
        User.objects.create(username=username, email=username)
        return User.objects.get(username=username)

    @staticmethod
    def new_resource(name=None, auth_url=None) -> Resource:
        # TODO: User call_command on add_openstack_resource instead of duplicating this
        resource_name = name or uuid.uuid4().hex

        Resource.objects.create(
            resource_type=ResourceType.objects.get(name='OpenStack'),
            parent_resource=None,
            name=resource_name,
            description='OpenStack test cloud environment',
            is_available=True,
            is_public=True,
            is_allocatable=True
        )
        openstack = Resource.objects.get(name=resource_name)

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_AUTH_URL),
            resource=openstack,
            value=auth_url or f'https://{resource_name}/identity/v3'
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_PROJECT_DOMAIN),
            resource=openstack,
            value='default'
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_USER_DOMAIN),
            resource=openstack,
            value='default'
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_IDP),
            resource=openstack,
            value='sso'
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_FEDERATION_PROTOCOL),
            resource=openstack,
            value='openid'
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_ROLE),
            resource=openstack,
            value='member'
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name='quantity_label'),
            resource=openstack,
            value='Units of computing to allocate to the project. 1 Unit = 1 Instance, 2 vCPU, 4G RAM'
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name='quantity_default_value'),
            resource=openstack,
            value=1
        )

        return openstack

    def new_project(self, title=None, pi=None) -> Project:
        title = title or uuid.uuid4().hex
        pi = pi or self.new_user()
        status = ProjectStatusChoice.objects.get(name='New')

        Project.objects.create(title=title, pi=pi, status=status)
        return Project.objects.get(title=title)

    def new_project_user(self, user, project, role='Manager', status='Active'):
        pu, _ = ProjectUser.objects.get_or_create(
            user=user,
            project=project,
            role=ProjectUserRoleChoice.objects.get(name=role),
            status=ProjectUserStatusChoice.objects.get(name=status)
        )
        return pu

    def new_allocation(self, project, resource, quantity):
        allocation, _ = Allocation.objects.get_or_create(
            project=project,
            justification='a justification for testing data',
            quantity=quantity,
            status=AllocationStatusChoice.objects.get(
                name='New')
        )
        allocation.resources.add(resource)
        return allocation

    def new_allocation_user(self, allocation, user):
        au, _ = AllocationUser.objects.get_or_create(
            allocation=allocation,
            user=user,
            status=AllocationUserStatusChoice.objects.get(name='Active')
        )
        return au
