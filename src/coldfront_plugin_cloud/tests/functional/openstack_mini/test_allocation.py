import os
import unittest
import uuid

from coldfront_plugin_cloud import attributes, openstack, tasks, utils
from coldfront_plugin_cloud.tests import base

from django.core.management import call_command
from keystoneclient.v3 import client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient


@unittest.skipUnless(os.getenv('FUNCTIONAL_TESTS'), 'Functional tests not enabled.')
class TestSmallOpenstack(base.TestBase):
    """
    In this test, make an allocation on a Openstack cluster with only the identity, 
    compute, and volume services enabled
    To test that no exceptions are raised when making the quota on the small cluster
    """
    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_openstack_resource(name='Devstack',
                                          auth_url=os.getenv('OS_AUTH_URL'))
        self.session = openstack.get_session_for_resource(self.resource)
        self.identity = client.Client(session=self.session)
        self.compute = novaclient.Client(session=self.session, version=2)
        self.volume = cinderclient.Client(session=self.session, version=3)
        self.networking = neutronclient.Client(session=self.session)
        self.role_member = self.identity.roles.find(name='member')

    def test_new_allocation_quota(self):
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

        # Check nova quota
        expected_nova_quota = {
            'instances': 1,
            'cores': 1,
            'ram': 4096,
        }
        actual_nova_quota = self.compute.quotas.get(openstack_project.id)
        for k, v in expected_nova_quota.items():
            self.assertEqual(actual_nova_quota.__getattr__(k), v)
