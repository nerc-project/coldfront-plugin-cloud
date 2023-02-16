import functools
import json
import logging
import os
import requests
from requests.auth import HTTPBasicAuth
import time
from simplejson.errors import JSONDecodeError

from coldfront_plugin_cloud import attributes, base, utils

QUOTA_KEY_MAPPING = {
    attributes.QUOTA_LIMITS_CPU: lambda x: {":limits.cpu": f"{x * 1000}m"},
    attributes.QUOTA_LIMITS_MEMORY: lambda x: {":limits.memory": f"{x}Mi"},
    attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: lambda x: {":limits.ephemeral-storage": f"{x}Gi"},
}


class ApiException(Exception):
    def __init__(self, message):
        self.message = message


class NotFound(ApiException):
    pass


class Conflict(ApiException):
    pass


class OpenShiftResourceAllocator(base.ResourceAllocator):

    resource_type = 'openshift'

    project_name_max_length = 63

    @functools.cached_property
    def session(self):
        var_name = utils.env_safe_name(self.resource.name)
        username = os.getenv(f'OPENSHIFT_{var_name}_USERNAME')
        password = os.getenv(f'OPENSHIFT_{var_name}_PASSWORD')

        session = requests.session()
        if username and password:
            session.auth = HTTPBasicAuth(username, password)

        functional_tests = os.environ.get('FUNCTIONAL_TESTS', '').lower()
        verify = os.getenv(f'OPENSHIFT_{var_name}_VERIFY', '').lower()
        if functional_tests == 'true' or verify == 'false':
            session.verify = False

        return session

    @staticmethod
    def check_response(response: requests.Response):
        if 200 <= response.status_code < 300:
            try:
                return response.json()
            except JSONDecodeError:
                # https://github.com/CCI-MOC/openshift-acct-mgt/issues/54
                return response.text
        if response.status_code == 404:
            raise NotFound(f"{response.status_code}: {response.text}")
        elif 'does not exist' in response.text or 'not found' in response.text:
            raise NotFound(f"{response.status_code}: {response.text}")
        elif 'already exists' in response.text:
            raise Conflict(f"{response.status_code}: {response.text}")
        else:
            raise ApiException(f"{response.status_code}: {response.text}")

    def create_project(self, suggested_project_name):
        sanitized_project_name = utils.get_sanitized_project_name(suggested_project_name)
        project_id = utils.get_unique_project_name(
            sanitized_project_name,
            max_length=self.project_name_max_length)
        project_name = project_id
        self._create_project(project_name, project_id)
        return self.Project(project_name, project_id)

    def set_quota(self, project_id):
        url = f"{self.auth_url}/projects/{project_id}/quota"
        payload = dict()
        for key, func in QUOTA_KEY_MAPPING.items():
            if x := self.allocation.get_attribute(key):
                payload.update(func(x))
        r = self.session.put(url, data=json.dumps({'Quota': payload}))
        self.check_response(r)

    def get_quota(self, project_id):
        url = f"{self.auth_url}/projects/{project_id}/quota"
        r = self.session.get(url)
        return self.check_response(r)

    def create_project_defaults(self, project_id):
        pass

    def disable_project(self, project_id):
        url = f"{self.auth_url}/projects/{project_id}"
        r = self.session.delete(url)
        self.check_response(r)

    def reactivate_project(self, project_id):
        project_name = self.allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME)
        try:
            self._create_project(project_name, project_id)
        except Conflict:
            # This is a reactivation of an already active project
            # most likely for a quota update
            pass

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
        try:
            r = self.session.put(url)
            self.check_response(r)
        except Conflict:
            pass

    def assign_role_on_user(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>
        url = (f"{self.auth_url}/users/{username}/projects/{project_id}"
               f"/roles/{self.member_role_name}")
        try:
            r = self.session.put(url)
            self.check_response(r)
        except Conflict:
            pass

    def remove_role_from_user(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>
        url = (f"{self.auth_url}/users/{username}/projects/{project_id}"
               f"/roles/{self.member_role_name}")
        r = self.session.delete(url)
        self.check_response(r)

    def _create_project(self, project_name, project_id):
        url = f"{self.auth_url}/projects/{project_id}"
        headers = {"Content-type": "application/json"}
        annotations = {"cf_project_id": str(self.allocation.project_id),
                       "cf_pi": self.allocation.project.pi.username}

        payload = {"displayName": project_name,
                   "annotations": annotations}
        r = self.session.put(url, data=json.dumps(payload), headers=headers)
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
