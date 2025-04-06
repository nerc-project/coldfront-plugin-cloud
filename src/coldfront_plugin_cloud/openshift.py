import functools
import json
import logging
import os
import requests
from requests.auth import HTTPBasicAuth
import time
from simplejson.errors import JSONDecodeError

import kubernetes
import kubernetes.dynamic.exceptions as kexc
from openshift.dynamic import DynamicClient

from coldfront_plugin_cloud import attributes, base, utils


logger = logging.getLogger(__name__)


API_PROJECT = "project.openshift.io/v1"
API_USER = "user.openshift.io/v1"
API_RBAC = "rbac.authorization.k8s.io/v1"
API_CORE = "v1"
IGNORED_ATTRIBUTES = [
    "resourceVersion",
    "creationTimestamp",
    "uid",
]

def clean_openshift_metadata(obj):
    if "metadata" in obj:
        for attr in IGNORED_ATTRIBUTES:
            if attr in obj["metadata"]:
                del obj["metadata"][attr]

    return obj

QUOTA_KEY_MAPPING = {
    attributes.QUOTA_LIMITS_CPU: lambda x: {":limits.cpu": f"{x * 1000}m"},
    attributes.QUOTA_LIMITS_MEMORY: lambda x: {":limits.memory": f"{x}Mi"},
    attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: lambda x: {":limits.ephemeral-storage": f"{x}Gi"},
    attributes.QUOTA_REQUESTS_STORAGE: lambda x: {":requests.storage": f"{x}Gi"},
    attributes.QUOTA_REQUESTS_GPU: lambda x: {":requests.nvidia.com/gpu": f"{x}"},
    attributes.QUOTA_PVC: lambda x: {":persistentvolumeclaims": f"{x}"},
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

    def __init__(self, resource, allocation):
        super().__init__(resource, allocation)
        self.safe_resource_name = utils.env_safe_name(resource.name)
        self.id_provider = resource.get_attribute(attributes.RESOURCE_IDENTITY_NAME)
        self.apis = {}

        self.functional_tests = os.environ.get("FUNCTIONAL_TESTS", "").lower()
        self.verify = os.getenv(f"OPENSHIFT_{self.safe_resource_name}_VERIFY", "").lower()

    @functools.cached_property
    def k8_client(self):
        # Load Endpoint URL and Auth token for new k8 client
        openshift_token = os.getenv(f"OPENSHIFT_{self.safe_resource_name}_TOKEN")
        openshift_url = self.resource.get_attribute(attributes.RESOURCE_API_URL)

        k8_config = kubernetes.client.Configuration()
        k8_config.api_key["authorization"] = openshift_token
        k8_config.api_key_prefix["authorization"] = "Bearer"
        k8_config.host = openshift_url

        if self.verify == "false":
            k8_config.verify_ssl = False
        else:
            k8_config.verify_ssl = True

        k8s_client = kubernetes.client.ApiClient(configuration=k8_config)
        return DynamicClient(k8s_client)

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
        
    def qualified_id_user(self, id_user):
        return f"{self.id_provider}:{id_user}"

    def get_resource_api(self, api_version: str, kind: str):
        """Either return the cached resource api from self.apis, or fetch a
        new one, store it in self.apis, and return it."""
        k = f"{api_version}:{kind}"
        api = self.apis.setdefault(
            k, self.k8_client.resources.get(api_version=api_version, kind=kind)
        )
        return api

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
            if (x := self.allocation.get_attribute(key)) is not None:
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
        if (
            self._openshift_user_exists(username)
            and self._openshift_identity_exists(username)
            and self._openshift_useridentitymapping_exists(username, username)
        ):
            return {'username': username}
        
        logger.info(f"User ({username}) does not exist")

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
        labels = {
            'opendatahub.io/dashboard': "true",
            'modelmesh-enabled': "true",
        }

        payload = {"displayName": project_name,
                   "annotations": annotations,
                   "labels": labels}
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

    def get_users(self, project_id):
        url = f"{self.auth_url}/projects/{project_id}/users"
        r = self.session.get(url)
        return set(self.check_response(r))
    
    def _openshift_get_user(self, username):
        api = self.get_resource_api(API_USER, "User")
        return clean_openshift_metadata(api.get(name=username).to_dict())
    
    def _openshift_get_identity(self, id_user):
        api = self.get_resource_api(API_USER, "Identity")
        return clean_openshift_metadata(
            api.get(name=self.qualified_id_user(id_user)).to_dict()
        )
    
    def _openshift_user_exists(self, user_name):
        try:
            self._openshift_get_user(user_name)
        except kexc.NotFoundError as e:
            # Ensures error raise because resource not found, 
            # not because of other reasons, like incorrect url
            e_info = json.loads(e.body)
            if e_info.get("reason") == "NotFound":
                return False
            raise e
        return True
    
    def _openshift_identity_exists(self, id_user):
        try:
            self._openshift_get_identity(id_user)
        except kexc.NotFoundError as e:
            e_info = json.loads(e.body)
            if e_info.get("reason") == "NotFound":
                return False
            raise e
        return True
    
    def _openshift_useridentitymapping_exists(self, user_name, id_user):
        try:
            user = self._openshift_get_user(user_name)
        except kexc.NotFoundError as e:
            e_info = json.loads(e.body)
            if e_info.get("reason") == "NotFound":
                return False
            raise e

        return any(
            identity == self.qualified_id_user(id_user)
            for identity in user.get("identities", [])
        )
    
