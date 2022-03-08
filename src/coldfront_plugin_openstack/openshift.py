import functools
import json
import os
import requests
from requests.auth import HTTPBasicAuth
import time
import uuid

from coldfront_plugin_openstack import attributes, base, utils


class ApiException(Exception):
    def __init__(self, message):
        self.message = message


class NotFound(ApiException):
    pass


class OpenShiftResourceAllocator(base.ResourceAllocator):

    resource_type = 'openshift'

    @functools.cached_property
    def session(self):
        var_name = utils.env_safe_name(self.resource.name)
        username = os.getenv(f'OPENSHIFT_{var_name}_USERNAME')
        password = os.getenv(f'OPENSHIFT_{var_name}_PASSWORD')

        session = requests.session()
        if username and password:
            session.auth = HTTPBasicAuth(username, password)
        if os.environ.get('FUNCTIONAL_TESTS', '') == 'True':
            session.verify = False
        return session

    @staticmethod
    def check_response(response: requests.Response):
        if 200 <= response.status_code < 300:
            return response.json()
        if response.status_code == 404:
            raise NotFound(f"{response.status_code}: {response.text}")
        elif 'does not exist' in response.text or 'not found' in response.text:
            raise NotFound(f"{response.status_code}: {response.text}")
        else:
            raise ApiException(f"{response.status_code}: {response.text}")

    def create_project(self, project_name):
        project_id = uuid.uuid4().hex
        self._create_project(project_name, project_id)
        return project_id

    def set_quota(self, project_id):
        pass

    def create_project_defaults(self, project_id):
        pass

    def disable_project(self, project_id):
        url = f"{self.auth_url}/projects/{project_id}"
        r = self.session.delete(url)
        self.check_response(r)

    def reactivate_project(self, project_id):
        project_name = self.allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME)
        self._create_project(project_name, project_id)

    def get_federated_user(self, username):
        url = f"{self.auth_url}/users/{username}"
        try:
            r = self.session.get(url)
            self.check_response(r)
            return {'username': username}
        except NotFound:
            pass

    def create_federated_user(self, unique_id):
        url = f"{self.auth_url}/users/{unique_id}"
        r = self.session.put(url)
        self.check_response(r)

    def assign_role_on_user(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>
        url = (f"{self.auth_url}/users/{username}/projects/{project_id}"
               f"/roles/{self.member_role_name}")
        r = self.session.put(url)
        self.check_response(r)

    def remove_role_from_user(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>
        url = (f"{self.auth_url}/users/{username}/projects/{project_id}"
               f"/roles/{self.member_role_name}")
        r = self.session.delete(url)
        self.check_response(r)

    def _create_project(self, project_name, project_id):
        url = f"{self.auth_url}/projects/{project_id}"
        payload = {"displayName": project_name}
        r = self.session.put(url, data=json.dumps(payload))
        self.check_response(r)

    def _get_role(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>
        url = (f"{self.auth_url}/users/{username}/projects/{project_id}"
               f"/roles/{self.member_role_name}")
        r = self.session.get(url)
        return self.check_response(r)

    def _get_project(self, project_id):
        url = f"{self.auth_url}/projects/{project_id}"
        r = self.session.get(url)
        return self.check_response(r)

    def _delete_user(self, username):
        url = f"{self.auth_url}/users/{username}"
        r = self.session.delete(url)
        return self.check_response(r)
