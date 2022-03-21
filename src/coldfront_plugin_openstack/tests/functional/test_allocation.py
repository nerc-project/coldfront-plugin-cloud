import os
import unittest

from coldfront_plugin_openstack import attributes, openstack, tasks, utils
from coldfront_plugin_openstack.tests import base

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient


@unittest.skipUnless(os.getenv('FUNCTIONAL_TESTS'), 'Functional tests not enabled.')
class TestAllocation(base.TestBase):

    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_resource(name='Devstack',
                                          auth_url=os.getenv('OS_AUTH_URL'))
        self.session = openstack.get_session_for_resource(self.resource)
        self.identity = client.Client(session=self.session)
        self.compute = novaclient.Client(
            openstack.QUOTA_KEY_MAPPING['compute']['version'],
            session=self.session
        )
        self.volume = cinderclient.Client(
            openstack.QUOTA_KEY_MAPPING['volume']['version'],
            session=self.session
        )
        self.networking = neutronclient.Client(session=self.session)
        self.role_member = self.identity.roles.find(name='member')

    def test_new_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openstack.OpenStackResourceAllocator(self.resource,
                                                         allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        # Check project
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        self.assertIsNotNone(project_id)
        self.assertIsNotNone(allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME))

        openstack_project = self.identity.projects.get(project_id)
        self.assertTrue(openstack_project.enabled)

        # Check user and roles
        openstack_user = allocator.get_federated_user(user.username)
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)

        # Check default network
        network = self.networking.list_networks(
            project_id=project_id, name='default_network')['networks'][0]
        router = self.networking.list_routers(
            project_id=project_id, name='default_router')['routers'][0]
        ports = self.networking.list_ports(project_id=project_id,
                                           network_id=network['id'],
                                           device_id=router['id'])['ports']
        self.assertIsNotNone(ports)
        self.assertEqual(ports[0]['status'], 'ACTIVE')

        # Check nova quota
        expected_nova_quota = {
            'instances': 1,
            'cores': 2,
            'ram': 4096,
        }
        actual_nova_quota = self.compute.quotas.get(openstack_project.id)
        for k, v in expected_nova_quota.items():
            self.assertEqual(actual_nova_quota.__getattr__(k), v)

        # Check cinder quota
        expected_cinder_quota = {
            'volumes': 2,
            'gigabytes': 100,
        }
        actual_cinder_quota = self.volume.quotas.get(openstack_project.id)
        for k, v in expected_cinder_quota.items():
            self.assertEqual(actual_cinder_quota.__getattr__(k), v)

        # Check neutron quota
        expected_neutron_quota = {
            'floatingip': 2,
        }
        actual_neutron_quota = self.networking.show_quota(openstack_project.id)['quota']
        for k, v in expected_neutron_quota.items():
            self.assertEqual(actual_neutron_quota.get(k), v)

        # Check correct attributes
        for attr in attributes.ALLOCATION_QUOTA_ATTRIBUTES:
            self.assertIsNotNone(allocation.get_attribute(attr))

    def test_new_allocation_with_quantity(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 3)
        allocator = openstack.OpenStackResourceAllocator(self.resource,
                                                         allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        # Check project
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        self.assertIsNotNone(project_id)
        self.assertIsNotNone(allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME))

        openstack_project = self.identity.projects.get(project_id)
        self.assertTrue(openstack_project.enabled)

        # Check user and roles
        openstack_user = allocator.get_federated_user(user.username)
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)

        # Check quota
        # Check nova quota
        expected_nova_quota = {
            'instances': 1 * 3,
            'cores': 2 * 3,
            'ram': 4096 * 3,
        }
        actual_nova_quota = self.compute.quotas.get(openstack_project.id)
        for k, v in expected_nova_quota.items():
            self.assertEqual(actual_nova_quota.__getattr__(k), v)

        # Check cinder quota
        expected_cinder_quota = {
            'volumes': 2 * 3,
            'gigabytes': 100 * 3,
        }
        actual_cinder_quota = self.volume.quotas.get(openstack_project.id)
        for k, v in expected_cinder_quota.items():
            self.assertEqual(actual_cinder_quota.__getattr__(k), v)

        # Check neutron quota
        expected_neutron_quota = {
            'floatingip': 2,
        }
        actual_neutron_quota = self.networking.show_quota(openstack_project.id)['quota']
        for k, v in expected_neutron_quota.items():
            self.assertEqual(actual_neutron_quota.get(k), v)

        # Change allocation attribute for floating ips and cores
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_FLOATING_IPS), 2)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_VCPU), 2 * 3)
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_FLOATING_IPS, 3)
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_VCPU, 100)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_FLOATING_IPS), 3)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_VCPU), 100)

        tasks.activate_allocation(allocation.pk)

        # Recheck neutron quota after attribute change
        new_neutron_quota = self.networking.show_quota(openstack_project.id)['quota']
        self.assertEqual(new_neutron_quota['floatingip'], 3)
        actual_nova_quota = self.compute.quotas.get(openstack_project.id)
        self.assertEqual(actual_nova_quota.__getattr__('cores'), 100)

    def test_reactivate_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openstack.OpenStackResourceAllocator(self.resource,
                                                         allocation)

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
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)

    def test_add_remove_user(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        project_user = self.new_project_user(user, project)
        allocation = self.new_allocation(project, self.resource, 1)
        allocation_user = self.new_allocation_user(allocation, user)
        allocator = openstack.OpenStackResourceAllocator(self.resource,
                                                         allocation)

        user2 = self.new_user()
        project_user2 = self.new_project_user(user2, project)
        allocation_user2 = self.new_allocation_user(allocation, user2)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        tasks.add_user_to_allocation(allocation_user2.pk)

        openstack_user = allocator.get_federated_user(user2.username)
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)

        tasks.remove_user_from_allocation(allocation_user2.pk)

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 0)

    def test_add_remove_user_existing(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        project_user = self.new_project_user(user, project)
        allocation = self.new_allocation(project, self.resource, 1)
        allocation_user = self.new_allocation_user(allocation, user)
        allocator = openstack.OpenStackResourceAllocator(self.resource,
                                                         allocation)

        user2 = self.new_user()
        project_user2 = self.new_project_user(user2, project)
        allocation_user2 = self.new_allocation_user(allocation, user2)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        # Create non-federated username beforehand
        self.identity.users.create(name=user2.username, domain='default')

        tasks.add_user_to_allocation(allocation_user2.pk)

        openstack_user = allocator.get_federated_user(user2.username)
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)

        tasks.remove_user_from_allocation(allocation_user2.pk)

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 0)

    def test_existing_user(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openstack.OpenStackResourceAllocator(self.resource,
                                                         allocation)

        # Create non-federated username beforehand
        self.identity.users.create(name=user.username, domain='default')

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        openstack_user = allocator.get_federated_user(user.username)
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)
