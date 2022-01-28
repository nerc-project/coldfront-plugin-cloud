import os
import unittest
import uuid

from coldfront_plugin_openstack import attributes
from coldfront_plugin_openstack import tasks
from coldfront_plugin_openstack.tests import base
from coldfront_plugin_openstack import keycloak

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client
from cinderclient import client as cinderclient
from neutronclient.v2_0 import client as neutronclient
from novaclient import client as novaclient


@unittest.skipUnless(os.getenv('KEYCLOAK_URL'), 'Keycloak not configured.')
@unittest.skipUnless(os.getenv('FUNCTIONAL_TESTS'), 'Functional tests not enabled.')
class TestImpersonate(base.TestBase):

    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_resource(name='Devstack',
                                          auth_url=os.getenv('OS_AUTH_URL'),
                                          supports_fed_attr='No')
        self.session = tasks.get_session_for_resource(self.resource)
        self.identity = client.Client(session=self.session)
        self.keycloak = keycloak.KeycloakClient(os.getenv('KEYCLOAK_URL'),
                                                os.getenv('KEYCLOAK_USER'),
                                                os.getenv('KEYCLOAK_PASS'))

    def test_impersonate_user_login(self):
        username = uuid.uuid4().hex
        self.keycloak.create_user('master', username, username, username, username)
        user = tasks.get_or_create_federated_user(self.resource, username)
        self.assertEqual(username, user['name'])
