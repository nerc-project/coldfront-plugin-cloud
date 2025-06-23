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


PROJECT_DEFAULT_LABELS = {
    "opendatahub.io/dashboard": "true",
    "modelmesh-enabled": "true",
    "nerc.mghpcc.org/allow-unencrypted-routes": "true",
    "nerc.mghpcc.org/project": "true",
}

LIMITRANGE_DEFAULTS = [
    {
        "type": "Container",
        "default": {"cpu": "1", "memory": "4096Mi", "nvidia.com/gpu": "0"},
        "defaultRequest": {"cpu": "500m", "memory": "2048Mi", "nvidia.com/gpu": "0"},
        "min": {"cpu": "125m", "memory": "256Mi"},
    }
]


def clean_openshift_metadata(obj):
    if "metadata" in obj:
        for attr in IGNORED_ATTRIBUTES:
            if attr in obj["metadata"]:
                del obj["metadata"][attr]

    return obj


class ApiException(Exception):
    def __init__(self, message):
        self.message = message


class NotFound(ApiException):
    pass


class Conflict(ApiException):
    pass


class OpenShiftResourceAllocator(base.ResourceAllocator):
    QUOTA_KEY_MAPPING = {
        attributes.QUOTA_LIMITS_CPU: lambda x: {"limits.cpu": f"{x * 1000}m"},
        attributes.QUOTA_LIMITS_MEMORY: lambda x: {"limits.memory": f"{x}Mi"},
        attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: lambda x: {
            "limits.ephemeral-storage": f"{x}Gi"
        },
        attributes.QUOTA_REQUESTS_STORAGE: lambda x: {"requests.storage": f"{x}Gi"},
        attributes.QUOTA_REQUESTS_GPU: lambda x: {"requests.nvidia.com/gpu": f"{x}"},
        attributes.QUOTA_PVC: lambda x: {"persistentvolumeclaims": f"{x}"},
    }

    resource_type = "openshift"

    project_name_max_length = 63

    def __init__(self, resource, allocation):
        super().__init__(resource, allocation)
        self.safe_resource_name = utils.env_safe_name(resource.name)
        self.id_provider = resource.get_attribute(attributes.RESOURCE_IDENTITY_NAME)
        self.apis = {}

        self.functional_tests = os.environ.get("FUNCTIONAL_TESTS", "").lower()
        self.verify = os.getenv(
            f"OPENSHIFT_{self.safe_resource_name}_VERIFY", ""
        ).lower()

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
        username = os.getenv(f"OPENSHIFT_{var_name}_USERNAME")
        password = os.getenv(f"OPENSHIFT_{var_name}_PASSWORD")

        session = requests.session()
        if username and password:
            session.auth = HTTPBasicAuth(username, password)

        functional_tests = os.environ.get("FUNCTIONAL_TESTS", "").lower()
        verify = os.getenv(f"OPENSHIFT_{var_name}_VERIFY", "").lower()
        if functional_tests == "true" or verify == "false":
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
        elif "does not exist" in response.text or "not found" in response.text:
            raise NotFound(f"{response.status_code}: {response.text}")
        elif "already exists" in response.text:
            raise Conflict(f"{response.status_code}: {response.text}")
        else:
            raise ApiException(f"{response.status_code}: {response.text}")

    @staticmethod
    def is_error_not_found(e_info):
        return e_info["reason"] == "NotFound"

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
        sanitized_project_name = utils.get_sanitized_project_name(
            suggested_project_name
        )
        project_id = utils.get_unique_project_name(
            sanitized_project_name, max_length=self.project_name_max_length
        )
        project_name = project_id
        self._create_project(project_name, project_id)
        return self.Project(project_name, project_id)

    def patch_project(self, project_id, new_project_spec):
        self._openshift_patch_namespace(project_id, new_project_spec)

    def delete_quotas(self, project_id):
        """deletes all resourcequotas from an openshift project"""
        resourcequotas = self._openshift_get_resourcequotas(project_id)
        for resourcequota in resourcequotas:
            self._openshift_delete_resourcequota(
                project_id, resourcequota["metadata"]["name"]
            )

        logger.info(f"All quotas for {project_id} successfully deleted")

    def set_quota(self, project_id):
        """Sets the quota for a project, creating a minimal resourcequota
        object in the project namespace with no extra scopes"""

        quota_spec = {}
        for key, func in self.QUOTA_KEY_MAPPING.items():
            if (x := self.allocation.get_attribute(key)) is not None:
                quota_spec.update(func(x))

        quota_def = {
            "metadata": {"name": f"{project_id}-project"},
            "spec": {"hard": quota_spec},
        }

        self.delete_quotas(project_id)
        self._openshift_create_resourcequota(project_id, quota_def)

        logger.info(f"Quota for {project_id} successfully created")

    def get_quota(self, project_id):
        cloud_quotas = self._openshift_get_resourcequotas(project_id)
        combined_quota = {}
        for cloud_quota in cloud_quotas:
            combined_quota.update(cloud_quota["spec"]["hard"])

        return combined_quota

    def create_project_defaults(self, project_id):
        pass

    def disable_project(self, project_id):
        self._openshift_delete_project(project_id)
        logger.info(f"Project {project_id} successfully deleted")

    def reactivate_project(self, project_id):
        project_name = self.allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME)
        try:
            self._create_project(project_name, project_id)
        except kexc.ConflictError:
            # This is a reactivation of an already active project
            # most likely for a quota update
            pass

    def get_federated_user(self, username):
        if (
            self._openshift_user_exists(username)
            and self._openshift_identity_exists(username)
            and self._openshift_useridentitymapping_exists(username, username)
        ):
            return {"username": username}

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
        url = (
            f"{self.auth_url}/users/{username}/projects/{project_id}"
            f"/roles/{self.member_role_name}"
        )
        try:
            r = self.session.put(url)
            self.check_response(r)
        except Conflict:
            pass

    def remove_role_from_user(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>
        url = (
            f"{self.auth_url}/users/{username}/projects/{project_id}"
            f"/roles/{self.member_role_name}"
        )
        r = self.session.delete(url)
        self.check_response(r)

    def _create_project(self, project_name, project_id):
        pi_username = self.allocation.project.pi.username

        annotations = {
            "cf_project_id": str(self.allocation.project_id),
            "cf_pi": pi_username,
            "openshift.io/display-name": project_name,
            "openshift.io/requester": pi_username,
        }

        project_def = {
            "metadata": {
                "name": project_name,
                "annotations": annotations,
                "labels": PROJECT_DEFAULT_LABELS,
            },
        }

        self._openshift_create_project(project_def)
        self._openshift_create_limits(project_name)

        logger.info(f"Project {project_id} and limit range successfully created")

    def _get_role(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>
        url = (
            f"{self.auth_url}/users/{username}/projects/{project_id}"
            f"/roles/{self.member_role_name}"
        )
        r = self.session.get(url)
        return self.check_response(r)

    def _get_project(self, project_id):
        return self._openshift_get_project(project_id)

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
            if (
                self.is_error_not_found(e_info)
                and e_info["details"]["name"] == user_name
            ):
                return False
            raise e
        return True

    def _openshift_identity_exists(self, id_user):
        try:
            self._openshift_get_identity(id_user)
        except kexc.NotFoundError as e:
            e_info = json.loads(e.body)
            if self.is_error_not_found(e_info):
                return False
            raise e
        return True

    def _openshift_useridentitymapping_exists(self, user_name, id_user):
        try:
            user = self._openshift_get_user(user_name)
        except kexc.NotFoundError as e:
            e_info = json.loads(e.body)
            if self.is_error_not_found(e_info):
                return False
            raise e

        return any(
            identity == self.qualified_id_user(id_user)
            for identity in user.get("identities", [])
        )

    def _openshift_get_project(self, project_name):
        api = self.get_resource_api(API_PROJECT, "Project")
        return clean_openshift_metadata(api.get(name=project_name).to_dict())

    def _openshift_create_project(self, project_def):
        api = self.get_resource_api(API_PROJECT, "Project")
        return api.create(body=project_def).to_dict()

    def _openshift_delete_project(self, project_name):
        api = self.get_resource_api(API_PROJECT, "Project")
        return api.delete(name=project_name).to_dict()

    def _openshift_get_limits(self, project_name):
        """
        project_name: project_name in which to get LimitRange
        """
        api = self.get_resource_api(API_CORE, "LimitRange")
        return clean_openshift_metadata(api.get(namespace=project_name).to_dict())

    def _openshift_create_limits(self, project_name, limits=None):
        """
        project_name: project_name in which to create LimitRange
        limits: dictionary of limits to create, or None for default
        """
        api = self.get_resource_api(API_CORE, "LimitRange")

        payload = {
            "metadata": {"name": f"{project_name.lower()}-limits"},
            "spec": {"limits": limits or LIMITRANGE_DEFAULTS},
        }
        return api.create(body=payload, namespace=project_name).to_dict()

    def _openshift_get_namespace(self, namespace_name):
        api = self.get_resource_api(API_CORE, "Namespace")
        return clean_openshift_metadata(api.get(name=namespace_name).to_dict())

    def _openshift_patch_namespace(self, project_name, new_project_spec):
        # During testing, apparently we can't patch Projects, but we can do so with Namespaces
        api = self.get_resource_api(API_CORE, "Namespace")
        api.patch(name=project_name, body=new_project_spec)

    def _openshift_get_resourcequotas(self, project_id):
        """Returns a list of resourcequota objects in namespace with name `project_id`"""
        # Raise a NotFound error if the project doesn't exist
        self._openshift_get_project(project_id)
        api = self.get_resource_api(API_CORE, "ResourceQuota")
        res = clean_openshift_metadata(api.get(namespace=project_id).to_dict())

        return res["items"]

    def _wait_for_quota_to_settle(self, project_id, resource_quota):
        """Wait for quota on resourcequotas to settle.

        When creating a new resourcequota that sets a quota on resourcequota objects, we need to
        wait for OpenShift to calculate the quota usage before we attempt to create any new
        resourcequota objects.
        """

        if "resourcequotas" in resource_quota["spec"]["hard"]:
            logger.info("waiting for resourcequota quota")

            api = self.get_resource_api(API_CORE, "ResourceQuota")
            while True:
                resp = clean_openshift_metadata(
                    api.get(
                        namespace=project_id, name=resource_quota["metadata"]["name"]
                    ).to_dict()
                )
                if "resourcequotas" in resp["status"].get("used", {}):
                    break
                time.sleep(0.1)

    def _openshift_create_resourcequota(self, project_id, quota_def):
        api = self.get_resource_api(API_CORE, "ResourceQuota")
        res = api.create(namespace=project_id, body=quota_def).to_dict()
        self._wait_for_quota_to_settle(project_id, res)

    def _openshift_delete_resourcequota(self, project_id, resourcequota_name):
        """In an openshift namespace {project_id) delete a specified resourcequota"""
        api = self.get_resource_api(API_CORE, "ResourceQuota")
        return api.delete(namespace=project_id, name=resourcequota_name).to_dict()
