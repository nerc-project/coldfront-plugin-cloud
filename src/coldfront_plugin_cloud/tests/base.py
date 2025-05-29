import os
from os import devnull
import sys
import uuid

from django.test import TestCase

from coldfront.core.allocation.models import (
    Allocation,
    AllocationStatusChoice,
    AllocationUser,
    AllocationUserStatusChoice,
)

from django.contrib.auth.models import User
from coldfront.core.project.models import (
    Project,
    ProjectUser,
    ProjectUserRoleChoice,
    ProjectUserStatusChoice,
    ProjectStatusChoice,
)
from coldfront.core.resource.models import Resource
from coldfront.core.field_of_science.models import FieldOfScience
from django.core.management import call_command


class TestBase(TestCase):
    def setUp(self) -> None:
        # Otherwise output goes to the terminal for every test that is run
        backup, sys.stdout = sys.stdout, open(devnull, "a")
        call_command("initial_setup", "-f")
        call_command("load_test_data")
        call_command("register_cloud_attributes")
        sys.stdout = backup

    @staticmethod
    def new_user(username=None) -> User:
        username = username or f"{uuid.uuid4().hex}@example.com"
        User.objects.create(username=username, email=username)
        return User.objects.get(username=username)

    @staticmethod
    def new_esi_resource(name=None, auth_url=None) -> Resource:
        resource_name = name or uuid.uuid4().hex

        call_command(
            "add_openstack_resource",
            name=resource_name,
            auth_url=auth_url or f"https://{resource_name}/identity/v3",
            projects_domain="default",
            users_domain="default",
            idp="sso",
            protocol="openid",
            role="member",
            public_network=os.getenv("OPENSTACK_PUBLIC_NETWORK_ID"),
            network_cidr="192.168.0.0/24",
            esi=True,
        )
        return Resource.objects.get(name=resource_name)

    @staticmethod
    def new_openstack_resource(name=None, auth_url=None) -> Resource:
        resource_name = name or uuid.uuid4().hex

        call_command(
            "add_openstack_resource",
            name=resource_name,
            auth_url=auth_url or f"https://{resource_name}/identity/v3",
            projects_domain="default",
            users_domain="default",
            idp="sso",
            protocol="openid",
            role="member",
            public_network=os.getenv("OPENSTACK_PUBLIC_NETWORK_ID"),
            network_cidr="192.168.0.0/24",
            esi=False,
        )
        return Resource.objects.get(name=resource_name)

    @staticmethod
    def new_openshift_resource(
        name=None, auth_url=None, api_url=None, idp=None, for_virtualization=False
    ) -> Resource:
        resource_name = name or uuid.uuid4().hex

        call_command(
            "add_openshift_resource",
            name=resource_name,
            auth_url=auth_url or "https://onboarding-onboarding.cluster.local",
            api_url=api_url or "https://onboarding-onboarding.cluster.local:6443",
            idp=idp or "developer",
            for_virtualization=for_virtualization,
        )
        return Resource.objects.get(name=resource_name)

    def new_project(self, title=None, pi=None) -> Project:
        title = title or uuid.uuid4().hex
        pi = pi or self.new_user()
        status = ProjectStatusChoice.objects.get(name="New")

        Project.objects.create(title=title, pi=pi, status=status)
        return Project.objects.get(title=title)

    def new_project_user(self, user, project, role="Manager", status="Active"):
        pu, _ = ProjectUser.objects.get_or_create(
            user=user,
            project=project,
            role=ProjectUserRoleChoice.objects.get(name=role),
            status=ProjectUserStatusChoice.objects.get(name=status),
        )
        return pu

    def new_allocation(self, project, resource, quantity) -> Allocation:
        allocation, _ = Allocation.objects.get_or_create(
            project=project,
            justification="a justification for testing data",
            quantity=quantity,
            status=AllocationStatusChoice.objects.get(name="Active"),
        )
        allocation.resources.add(resource)
        return allocation

    def new_allocation_user(self, allocation, user):
        au, _ = AllocationUser.objects.get_or_create(
            allocation=allocation,
            user=user,
            status=AllocationUserStatusChoice.objects.get(name="Active"),
        )
        return au

    def new_field_of_science(self, description=None):
        description = description or uuid.uuid4().hex
        fos, _ = FieldOfScience.objects.get_or_create(
            is_selectable=True, description=description
        )
        return fos
