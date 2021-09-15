import os
import unittest
from unittest import mock

from coldfront.core.allocation.models import Allocation
from coldfront.core.resource.models import Resource

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
                                          auth_url='http://localhost:5000')
        self.session = tasks.get_session_for_resource(self.resource)
        self.identity = client.Client(session=self.session)
        self.compute = novaclient.Client(tasks.NOVA_VERSION,
                                         session=self.session)

    def test_new_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        self.assertIsNotNone(project_id)
        self.assertIsNotNone(allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME))

        openstack_project = self.identity.projects.get(project_id)
        self.assertTrue(openstack_project.enabled)

        # TODO: Assert correct quota

    def test_reactivate_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)

        tasks.activate_allocation(allocation.pk)

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)
        openstack_project.update(enabled=False)

        tasks.activate_allocation(allocation.pk)  # noqa
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)
        self.assertTrue(openstack_project.enabled)

        # TODO: assert quotas match expected quotas

    def test_add_user(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        project_user = self.new_project_user(user, project)
        allocation = self.new_allocation(project, self.resource, 1)
        allocation_user = self.new_allocation_user(allocation, user)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        openstack_project = self.identity.projects.get(project_id)

        tasks.add_user_to_allocation(allocation_user.pk)

        # TODO: check user created in openstack
        # TODO: check user has roles assignmed in openstack
