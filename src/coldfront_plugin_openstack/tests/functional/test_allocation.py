import os
import unittest

from coldfront_plugin_openstack import attributes
from coldfront_plugin_openstack import tasks
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
        self.session = tasks.get_session_for_resource(self.resource)
        self.identity = client.Client(session=self.session)
        self.compute = novaclient.Client(tasks.NOVA_VERSION,
                                         session=self.session)
        self.volume = cinderclient.Client(tasks.CINDER_VERSION,
                                          session=self.session)
        self.role_member = self.identity.roles.find(name='member')

    def test_new_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        # Check project
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        self.assertIsNotNone(project_id)
        self.assertIsNotNone(allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME))

        openstack_project = self.identity.projects.get(project_id)
        self.assertTrue(openstack_project.enabled)

        # Check user and roles
        openstack_user = tasks.get_federated_user(self.resource, user.username)
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)

        # Check quota
        union_key_mappings = dict(tasks.NOVA_KEY_MAPPING, **tasks.CINDER_KEY_MAPPING)
        expected_quotas = {
            union_key_mappings[x]: tasks.UNIT_TO_QUOTA_MAPPING[x]
            for x in attributes.ALLOCATION_QUOTA_ATTRIBUTES
        }
        actual_quotas = dict(
            self.compute.quotas.get(openstack_project.id).to_dict(),
            **self.volume.quotas.get(openstack_project.id).to_dict()
        )
        self.assertEqual(actual_quotas, dict(expected_quotas, **actual_quotas))

    def test_new_allocation_with_quantity(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 3)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        # Check project
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        self.assertIsNotNone(project_id)
        self.assertIsNotNone(allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME))

        openstack_project = self.identity.projects.get(project_id)
        self.assertTrue(openstack_project.enabled)

        # Check user and roles
        openstack_user = tasks.get_federated_user(self.resource, user.username)
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)

        # Check quota
        union_key_mappings = dict(tasks.NOVA_KEY_MAPPING, **tasks.CINDER_KEY_MAPPING)
        expected_quotas = {
            union_key_mappings[x]: tasks.UNIT_TO_QUOTA_MAPPING[x] * 3
            for x in attributes.ALLOCATION_QUOTA_ATTRIBUTES
        }
        actual_quotas = dict(
            self.compute.quotas.get(openstack_project.id).to_dict(),
            **self.volume.quotas.get(openstack_project.id).to_dict()
        )
        self.assertEqual(actual_quotas, dict(expected_quotas, **actual_quotas))

    def test_reactivate_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)

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
        openstack_user = tasks.get_federated_user(self.resource, user.username)
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

        user2 = self.new_user()
        project_user2 = self.new_project_user(user2, project)
        allocation_user2 = self.new_allocation_user(allocation, user2)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        tasks.add_user_to_allocation(allocation_user2.pk)

        openstack_user = tasks.get_federated_user(self.resource, user2.username)
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

        openstack_user = tasks.get_federated_user(self.resource, user2.username)
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

        # Create non-federated username beforehand
        self.identity.users.create(name=user.username, domain='default')

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        openstack_user = tasks.get_federated_user(self.resource, user.username)
        openstack_user = self.identity.users.get(openstack_user['id'])

        roles = self.identity.role_assignments.list(user=openstack_user.id,
                                                    project=openstack_project.id)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role['id'], self.role_member.id)
