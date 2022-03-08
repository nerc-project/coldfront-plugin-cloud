import os
import time
import unittest

from coldfront_plugin_openstack import attributes, openshift, tasks, utils
from coldfront_plugin_openstack.tests import base


@unittest.skipUnless(os.getenv('FUNCTIONAL_TESTS'), 'Functional tests not enabled.')
class TestAllocation(base.TestBase):

    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_openshift_resource(
            name='Microshift',
            auth_url=os.getenv('OS_AUTH_URL')
        )

    def test_new_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openshift.OpenShiftResourceAllocator(self.resource,
                                                         allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        # Check project
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        self.assertIsNotNone(project_id)
        self.assertIsNotNone(allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME))

        allocator._get_project(project_id)

        # Check user and roles
        allocator.get_federated_user(user.username)

        allocator._get_role(user.username, project_id)

        allocator.remove_role_from_user(user.username, project_id)

        with self.assertRaises(openshift.NotFound):
            allocator._get_role(user.username, project_id)

    def test_add_remove_user(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        project_user = self.new_project_user(user, project)
        allocation = self.new_allocation(project, self.resource, 1)
        allocation_user = self.new_allocation_user(allocation, user)
        allocator = openshift.OpenShiftResourceAllocator(self.resource,
                                                         allocation)

        user2 = self.new_user()
        project_user2 = self.new_project_user(user2, project)
        allocation_user2 = self.new_allocation_user(allocation, user2)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        tasks.add_user_to_allocation(allocation_user2.pk)
        allocator._get_role(user.username, project_id)

        allocator.get_federated_user(user2.username)

        allocator._get_role(user.username, project_id)
        allocator._get_role(user2.username, project_id)

        tasks.remove_user_from_allocation(allocation_user2.pk)

        allocator._get_role(user.username, project_id)
        with self.assertRaises(openshift.NotFound):
            allocator._get_role(user2.username, project_id)
