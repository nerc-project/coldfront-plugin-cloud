import os
import unittest
from unittest import mock
import uuid
import time

from coldfront_plugin_cloud import attributes, openstack, tasks, utils
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
        self.resource = self.new_openstack_resource(
            name="Devstack", auth_url=os.getenv("OS_AUTH_URL")
        )
        self.session = openstack.get_session_for_resource(self.resource)
        self.identity = client.Client(session=self.session)
        self.compute = novaclient.Client(session=self.session, version=2)
        self.volume = cinderclient.Client(session=self.session, version=3)
        self.networking = neutronclient.Client(session=self.session)
        self.role_member = self.identity.roles.find(name="member")

    def test_new_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openstack.OpenStackResourceAllocator(self.resource, allocation)

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
        # Port build-up time is not instant
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

        # Check nova quota
        expected_nova_quota = {
            "instances": 1,
            "cores": 1,
            "ram": 4096,
        }
        actual_nova_quota = self.compute.quotas.get(openstack_project.id)
        for k, v in expected_nova_quota.items():
            self.assertEqual(actual_nova_quota.__getattr__(k), v)

        # Check cinder quota
        expected_cinder_quota = {
            "volumes": 2,
            "gigabytes": 20,
        }
        actual_cinder_quota = self.volume.quotas.get(openstack_project.id)
        for k, v in expected_cinder_quota.items():
            self.assertEqual(actual_cinder_quota.__getattr__(k), v)

        # Check neutron quota
        expected_neutron_quota = {
            "floatingip": 2,
        }
        actual_neutron_quota = self.networking.show_quota(openstack_project.id)["quota"]
        for k, v in expected_neutron_quota.items():
            self.assertEqual(actual_neutron_quota.get(k), v)

        # Validate get_quota
        expected_quota = {
            "instances": 1,
            "cores": 1,
            "ram": 4096,
            "volumes": 2,
            "gigabytes": 20,
            "floatingip": 2,
            "x-account-meta-quota-bytes": 1,
        }
        resulting_quota = allocator.get_quota(openstack_project.id)
        if "x-account-meta-quota-bytes" not in resulting_quota.keys():
            expected_quota.pop("x-account-meta-quota-bytes")
        self.assertEqual(expected_quota, resulting_quota)

        # Check correct attributes
        for attr in attributes.ALLOCATION_QUOTA_ATTRIBUTES:
            if "OpenStack" in attr.name:
                self.assertIsNotNone(allocation.get_attribute(attr.name))

    def test_new_allocation_with_quantity(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 3)
        allocator = openstack.OpenStackResourceAllocator(self.resource, allocation)

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

        # Check quota
        # Check nova quota
        expected_nova_quota = {
            "instances": 1 * 3,
            "cores": 1 * 3,
            "ram": 4096 * 3,
        }
        actual_nova_quota = self.compute.quotas.get(openstack_project.id)
        for k, v in expected_nova_quota.items():
            self.assertEqual(actual_nova_quota.__getattr__(k), v)

        # Check cinder quota
        expected_cinder_quota = {
            "volumes": 2 * 3,
            "gigabytes": 20 * 3,
        }
        actual_cinder_quota = self.volume.quotas.get(openstack_project.id)
        for k, v in expected_cinder_quota.items():
            self.assertEqual(actual_cinder_quota.__getattr__(k), v)

        # Check neutron quota
        expected_neutron_quota = {
            "floatingip": 2,
        }
        actual_neutron_quota = self.networking.show_quota(openstack_project.id)["quota"]
        for k, v in expected_neutron_quota.items():
            self.assertEqual(actual_neutron_quota.get(k), v)

        # Change allocation attribute for floating ips, cores and storage
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_FLOATING_IPS), 2)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_VCPU), 1 * 3)
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_FLOATING_IPS, 3)
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_VCPU, 100)
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_VOLUMES_GB, 0)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_FLOATING_IPS), 3)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_VCPU), 100)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_VOLUMES_GB), 0)

        tasks.activate_allocation(allocation.pk)

        # Recheck neutron quota after attribute change
        new_neutron_quota = self.networking.show_quota(openstack_project.id)["quota"]
        self.assertEqual(new_neutron_quota["floatingip"], 3)
        actual_nova_quota = self.compute.quotas.get(openstack_project.id)
        self.assertEqual(actual_nova_quota.__getattr__("cores"), 100)
        actual_cinder_quota = self.volume.quotas.get(openstack_project.id)
        self.assertEqual(actual_cinder_quota.__getattr__("gigabytes"), 0)

        # Change allocation attributes for floating ips and cores again
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_FLOATING_IPS, 6)
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_VCPU, 200)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_FLOATING_IPS), 6)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_VCPU), 200)

        call_command("validate_allocations", apply=True)

        # Recheck neutron quota after attribute change
        new_neutron_quota = self.networking.show_quota(openstack_project.id)["quota"]
        self.assertEqual(new_neutron_quota["floatingip"], 6)
        actual_nova_quota = self.compute.quotas.get(openstack_project.id)
        self.assertEqual(actual_nova_quota.__getattr__("cores"), 200)

        # Change allocation attributes for object store quota
        current_quota = allocator.get_quota(openstack_project.id)
        obj_key = openstack.OpenStackResourceAllocator.QUOTA_KEY_MAPPING["object"][
            "keys"
        ][attributes.QUOTA_OBJECT_GB]
        if obj_key in current_quota.keys():
            utils.set_attribute_on_allocation(allocation, attributes.QUOTA_OBJECT_GB, 6)
            self.assertEqual(allocation.get_attribute(attributes.QUOTA_OBJECT_GB), 6)
            tasks.activate_allocation(allocation.pk)
            self.assertEqual(
                allocation.get_attribute(attributes.QUOTA_OBJECT_GB),
                allocator.get_quota(openstack_project.id)[obj_key],
            )

            # setting 0 object quota in coldfront -> 1 byte quota in swift/rgw
            utils.set_attribute_on_allocation(allocation, attributes.QUOTA_OBJECT_GB, 0)
            self.assertEqual(allocation.get_attribute(attributes.QUOTA_OBJECT_GB), 0)
            tasks.activate_allocation(allocation.pk)
            obj_quota = allocator.object(project_id).head_account().get(obj_key)
            self.assertEqual(int(obj_quota), 1)

            # test validate_allocations works for object quota set to 0
            utils.set_attribute_on_allocation(allocation, attributes.QUOTA_OBJECT_GB, 3)
            self.assertEqual(allocation.get_attribute(attributes.QUOTA_OBJECT_GB), 3)
            tasks.activate_allocation(allocation.pk)
            self.assertEqual(
                allocation.get_attribute(attributes.QUOTA_OBJECT_GB),
                allocator.get_quota(openstack_project.id)[obj_key],
            )
            utils.set_attribute_on_allocation(allocation, attributes.QUOTA_OBJECT_GB, 0)
            self.assertEqual(allocation.get_attribute(attributes.QUOTA_OBJECT_GB), 0)
            call_command("validate_allocations", apply=True)
            obj_quota = allocator.object(project_id).head_account().get(obj_key)
            self.assertEqual(int(obj_quota), 1)

    def test_reactivate_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openstack.OpenStackResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)

        # Check project
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)
        openstack_project.update(enabled=False)

        tasks.activate_allocation(allocation.pk)  # noqa
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
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

    def test_add_remove_user(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        self.new_project_user(user, project)
        allocation = self.new_allocation(project, self.resource, 1)
        self.new_allocation_user(allocation, user)
        allocator = openstack.OpenStackResourceAllocator(self.resource, allocation)

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

        # directly add a user to openstack which should then be
        # deleted when validate_allocations is called
        non_coldfront_user = uuid.uuid4().hex
        allocator.get_or_create_federated_user(non_coldfront_user)
        allocator.assign_role_on_user(non_coldfront_user, project_id)
        assert non_coldfront_user in allocator.get_users(project_id)
        call_command("validate_allocations", apply=True)
        assert non_coldfront_user not in allocator.get_users(project_id)

    def test_add_remove_user_existing(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        self.new_project_user(user, project)
        allocation = self.new_allocation(project, self.resource, 1)
        self.new_allocation_user(allocation, user)
        allocator = openstack.OpenStackResourceAllocator(self.resource, allocation)

        user2 = self.new_user()
        self.new_project_user(user2, project)
        allocation_user2 = self.new_allocation_user(allocation, user2)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        # Create non-federated username beforehand
        self.identity.users.create(name=user2.username, domain="default")

        tasks.add_user_to_allocation(allocation_user2.pk)

        openstack_user = allocator.get_federated_user(user2.username)
        openstack_user = self.identity.users.get(openstack_user["id"])

        roles = self.identity.role_assignments.list(
            user=openstack_user.id, project=openstack_project.id
        )

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role["id"], self.role_member.id)

        tasks.remove_user_from_allocation(allocation_user2.pk)

        roles = self.identity.role_assignments.list(
            user=openstack_user.id, project=openstack_project.id
        )

        self.assertEqual(len(roles), 0)

    def test_existing_user(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openstack.OpenStackResourceAllocator(self.resource, allocation)

        # Create non-federated username beforehand
        self.identity.users.create(name=user.username, domain="default")

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        openstack_user = allocator.get_federated_user(user.username)
        openstack_user = self.identity.users.get(openstack_user["id"])

        roles = self.identity.role_assignments.list(
            user=openstack_user.id, project=openstack_project.id
        )

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role["id"], self.role_member.id)

    @mock.patch.object(
        tasks,
        "UNIT_QUOTA_MULTIPLIERS",
        {
            "openstack": {
                attributes.QUOTA_VCPU: 1,
            }
        },
    )
    def test_allocation_new_attribute(self):
        """When a new attribute is introduced, but pre-existing allocations don't have it"""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        self.assertEqual(allocation.get_attribute(attributes.QUOTA_VCPU), 2 * 1)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_RAM), None)

        # Check Openstack does have a non-zero default ram quota
        actual_nova_quota = self.compute.quotas.get(project_id)
        default_ram_quota = actual_nova_quota.ram
        self.assertEqual(actual_nova_quota.cores, 2)
        self.assertTrue(default_ram_quota > 0)

        # Add a new attribute for Openshift
        # Since Openstack already provided defaults, Coldfront should use those
        tasks.UNIT_QUOTA_MULTIPLIERS["openstack"][attributes.QUOTA_RAM] = 4096

        call_command("validate_allocations", apply=True)
        allocation.refresh_from_db()

        self.assertEqual(allocation.get_attribute(attributes.QUOTA_VCPU), 2 * 1)
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_RAM), default_ram_quota
        )

        expected_nova_quota = {
            "cores": 2,
            "ram": default_ram_quota,
        }
        actual_nova_quota = self.compute.quotas.get(project_id)
        for k, v in expected_nova_quota.items():
            self.assertEqual(actual_nova_quota.__getattr__(k), v)
