import os
import unittest
import uuid
import time

from coldfront_plugin_cloud import attributes, openstack, esi, tasks
from coldfront_plugin_cloud.tests import base

from django.core.management import call_command
from keystoneclient.v3 import client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient


@unittest.skipUnless(os.getenv("FUNCTIONAL_TESTS"), "Functional tests not enabled.")
class TestAllocation(base.TestBase):
    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_esi_resource(
            name="ESI", auth_url=os.getenv("OS_AUTH_URL")
        )
        self.session = openstack.get_session_for_resource(self.resource)
        self.identity = client.Client(session=self.session)
        self.compute = novaclient.Client(session=self.session, version=2)
        self.volume = cinderclient.Client(session=self.session, version=3)
        self.networking = neutronclient.Client(session=self.session)
        self.role_member = self.identity.roles.find(name="member")

    def test_new_ESI_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = esi.ESIResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        # Check project
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        self.assertIsNotNone(project_id)
        self.assertIsNotNone(
            allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME)
        )

        openstack_project = self.identity.projects.get(project_id)
        self.assertTrue(openstack_project.enabled)

        # Check user and roles
        openstack_user = allocator.get_federated_user(user.username)
        openstack_user = self.identity.users.get(openstack_user["id"])

        roles = self.identity.role_assignments.list(
            user=openstack_user.id, project=openstack_project.id
        )

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role["id"], self.role_member.id)

        # Check default network
        time.sleep(5)
        network = self.networking.list_networks(
            project_id=project_id, name="default_network"
        )["networks"][0]
        router = self.networking.list_routers(
            project_id=project_id, name="default_router"
        )["routers"][0]
        ports = self.networking.list_ports(
            project_id=project_id, network_id=network["id"], device_id=router["id"]
        )["ports"]
        self.assertIsNotNone(ports)
        self.assertEqual(ports[0]["status"], "ACTIVE")

        # Validate get_quota
        expected_quota = {
            "floatingip": 1,
            "network": 1,
        }
        resulting_quota = allocator.get_quota(openstack_project.id)
        self.assertEqual(expected_quota, resulting_quota)

    def test_add_remove_user(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        self.new_project_user(user, project)
        allocation = self.new_allocation(project, self.resource, 1)
        self.new_allocation_user(allocation, user)
        allocator = esi.ESIResourceAllocator(self.resource, allocation)

        user2 = self.new_user()
        self.new_project_user(user2, project)
        allocation_user2 = self.new_allocation_user(allocation, user2)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        tasks.add_user_to_allocation(allocation_user2.pk)

        openstack_user = allocator.get_federated_user(user2.username)
        openstack_user = self.identity.users.get(openstack_user["id"])

        roles = self.identity.role_assignments.list(
            user=openstack_user.id, project=openstack_project.id
        )

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role["id"], self.role_member.id)
        assert set([user.username, user2.username]) == allocator.get_users(project_id)

        tasks.remove_user_from_allocation(allocation_user2.pk)

        roles = self.identity.role_assignments.list(
            user=openstack_user.id, project=openstack_project.id
        )

        self.assertEqual(len(roles), 0)
        assert set([user.username]) == allocator.get_users(project_id)

        # use the validate_allocations command to add a new user
        user3 = self.new_user()
        self.new_allocation_user(allocation, user3)
        assert user3.username not in allocator.get_users(project_id)
        call_command("validate_allocations", apply=True)
        assert user3.username in allocator.get_users(project_id)

        non_coldfront_user = uuid.uuid4().hex
        allocator.get_or_create_federated_user(non_coldfront_user)
        allocator.assign_role_on_user(non_coldfront_user, project_id)
        assert non_coldfront_user in allocator.get_users(project_id)
        call_command("validate_allocations", apply=True)
        assert non_coldfront_user not in allocator.get_users(project_id)
