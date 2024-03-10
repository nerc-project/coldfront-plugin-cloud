import os
import unittest
import uuid

from coldfront_plugin_cloud import esi
from coldfront_plugin_cloud.tests import base

from django.core.management import call_command
from keystoneclient.v3 import client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient

@unittest.skipUnless(os.getenv('FUNCTIONAL_TESTS'), 'Functional tests not enabled.')
class TestAllocation(base.TestBase):

    # (Quan Pham) TODO What are the test cases for an ESI resource?
    # What do we need to test?

    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_esi_resource(name='ESI',
                                          auth_url=os.getenv('OS_AUTH_URL'))
        self.session = esi.get_session_for_resource(self.resource)
        self.identity = client.Client(session=self.session)
        self.compute = novaclient.Client(session=self.session, version=2)
        self.volume = cinderclient.Client(session=self.session, version=3)
        self.networking = neutronclient.Client(session=self.session)
        self.role_member = self.identity.roles.find(name='member')

    def test_new_ESI_allocation(self):
        pass
