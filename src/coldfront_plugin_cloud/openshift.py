import functools
import json
import logging
import os
import time
import re
import copy
from collections import namedtuple

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
        "min": {"cpu": "1m", "memory": "1Ki"},
    }
]


OPENSHIFT_ROLES = ["admin", "edit", "view"]


def clean_openshift_metadata(obj):
    if "metadata" in obj:
        for attr in IGNORED_ATTRIBUTES:
            if attr in obj["metadata"]:
                del obj["metadata"][attr]

    return obj


def parse_quota_value(quota_str: str | None, attr: str) -> int | None:
    PATTERN = r"([0-9]+)(m|k|Ki|Mi|Gi|Ti|Pi|Ei|K|M|G|T|P|E)?"

    suffix = {
        "Ki": 2**10,
        "Mi": 2**20,
        "Gi": 2**30,
        "Ti": 2**40,
        "Pi": 2**50,
        "Ei": 2**60,
        "m": 10**-3,
        "k": 10**3,
        "K": 10**3,
        "M": 10**6,
        "G": 10**9,
        "T": 10**12,
        "P": 10**15,
        "E": 10**18,
    }

    if quota_str and quota_str != "0":
        result = re.search(PATTERN, quota_str)

        if result is None:
            raise ValueError(f"Unable to parse quota_str = '{quota_str}' for {attr}")

        value = int(result.groups()[0])
        unit = result.groups()[1]

        # Convert to number i.e. without any unit suffix

        if unit is not None:
            quota_str = value * suffix[unit]
        else:
            quota_str = value

        # Convert some attributes to units that coldfront uses

        if "RAM" in attr:
            quota_str = round(quota_str / suffix["Mi"])
        elif "Storage" in attr:
            quota_str = round(quota_str / suffix["Gi"])
    elif quota_str and quota_str == "0":
        quota_str = 0

    return quota_str


LimitRangeDifference = namedtuple("LimitRangeDifference", ["key", "expected", "actual"])


def limit_ranges_diff(
    expected_lr_list: list[dict], actual_lr_list: list[dict]
) -> list[LimitRangeDifference]:
    expected_lr = copy.deepcopy(expected_lr_list[0])
    actual_lr = copy.deepcopy(actual_lr_list[0])
    differences = []

    for key in expected_lr | actual_lr:
        if key == "type":
            if actual_lr.get(key) != expected_lr.get(key):
                differences.append(
                    LimitRangeDifference(
                        key, expected_lr.get(key), actual_lr.get("type")
                    )
                )
                break
            continue

        # Extra fields in actual limit range, so else statement should only be expected fields
        if key not in expected_lr:
            differences.append(LimitRangeDifference(key, None, actual_lr[key]))
        else:
            for resource in expected_lr.setdefault(key, {}) | actual_lr.setdefault(
                key, {}
            ):
                expected_value = parse_quota_value(
                    expected_lr[key].get(resource), resource
                )
                actual_value = parse_quota_value(actual_lr[key].get(resource), resource)
                if expected_value != actual_value:
                    differences.append(
                        LimitRangeDifference(
                            f"{key},{resource}", expected_value, actual_value
                        )
                    )

    return differences


class ApiException(Exception):
    def __init__(self, message):
        self.message = message


class NotFound(ApiException):
    pass


class OpenShiftResourceAllocator(base.ResourceAllocator):
    QUOTA_KEY_MAPPING = {
        attributes.QUOTA_LIMITS_CPU: lambda x: {"limits.cpu": f"{x * 1000}m"},
        attributes.QUOTA_LIMITS_MEMORY: lambda x: {"limits.memory": f"{x}Mi"},
        attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: lambda x: {
            "limits.ephemeral-storage": f"{x}Gi"
        },
        attributes.QUOTA_REQUESTS_NESE_STORAGE: lambda x: {
            "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": f"{x}Gi"
        },
        attributes.QUOTA_REQUESTS_IBM_STORAGE: lambda x: {
            "ibm-spectrum-scale-fileset.storageclass.storage.k8s.io/requests.storage": f"{x}Gi"
        },
        attributes.QUOTA_REQUESTS_GPU: lambda x: {"requests.nvidia.com/gpu": f"{x}"},
        attributes.QUOTA_PVC: lambda x: {"persistentvolumeclaims": f"{x}"},
    }

    resource_type = "openshift"

    project_name_max_length = 45

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

    def set_project_configuration(self, project_id, dry_run=False):
        def _recreate_limitrange():
            if not dry_run:
                self._openshift_delete_limits(project_id)
                self._openshift_create_limits(project_id)
            logger.info(f"Recreated LimitRanges for namespace {project_id}.")

        limits = self._openshift_get_limits(project_id).get("items", [])

        if not limits:
            if not dry_run:
                self._openshift_create_limits(project_id)
            logger.info(f"Created default LimitRange for namespace {project_id}.")

        elif len(limits) > 1:
            logger.warning(
                f"More than one LimitRange found for namespace {project_id}."
            )
            _recreate_limitrange()

        if len(limits) == 1:
            actual_limits = limits[0]["spec"]["limits"]
            if len(actual_limits) != 1:
                logger.info(
                    f"LimitRange for more than one object type found for namespace {project_id}."
                )
                _recreate_limitrange()
            elif differences := limit_ranges_diff(LIMITRANGE_DEFAULTS, actual_limits):
                for difference in differences:
                    logger.info(
                        f"LimitRange for {project_id} differs {difference.key}: expected {difference.expected} but found {difference.actual}"
                    )
                _recreate_limitrange()

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
            if quota_spec := cloud_quota["spec"].get("hard"):
                combined_quota.update(quota_spec)

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
        user_def = {
            "metadata": {"name": unique_id},
            "fullName": unique_id,
        }

        identity_def = {
            "providerName": self.id_provider,
            "providerUserName": unique_id,
        }

        identity_mapping_def = {
            "user": {"name": unique_id},
            "identity": {"name": self.qualified_id_user(unique_id)},
        }

        self._openshift_create_user(user_def)
        self._openshift_create_identity(identity_def)
        self._openshift_create_useridentitymapping(identity_mapping_def)
        logger.info(f"User {unique_id} successfully created")

    def assign_role_on_user(self, username, project_id):
        """Assign a role to a user in a project using direct OpenShift API calls"""
        try:
            # Try to get existing rolebindings with same name
            # as the role name in project's namespace
            rolebinding = self._openshift_get_rolebindings(
                project_id, self.member_role_name
            )

            if not self._user_in_rolebinding(username, rolebinding):
                # Add user to existing rolebinding
                if "subjects" not in rolebinding:
                    rolebinding["subjects"] = []
                rolebinding["subjects"].append({"kind": "User", "name": username})
                self._openshift_update_rolebindings(project_id, rolebinding)

        except kexc.NotFoundError:
            # Create new rolebinding if it doesn't exist
            self._openshift_create_rolebindings(
                project_id, username, self.member_role_name
            )
        except kexc.ConflictError:
            # Role already exists, ignore
            pass

    def remove_role_from_user(self, username, project_id):
        """Remove a role from a user in a project using direct OpenShift API calls"""
        try:
            rolebinding = self._openshift_get_rolebindings(
                project_id, self.member_role_name
            )

            if "subjects" in rolebinding:
                rolebinding["subjects"] = [
                    subject
                    for subject in rolebinding["subjects"]
                    if not (
                        subject.get("kind") == "User"
                        and subject.get("name") == username
                    )
                ]
                self._openshift_update_rolebindings(project_id, rolebinding)

        except kexc.NotFoundError:
            # Rolebinding doesn't exist, nothing to remove
            pass

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
        rolebindings = self._openshift_get_rolebindings(
            project_id, self.member_role_name
        )
        if not self._user_in_rolebinding(username, rolebindings):
            raise NotFound(
                f"User {username} has no rolebindings in project {project_id}"
            )

    def _get_project(self, project_id):
        return self._openshift_get_project(project_id)

    def _delete_user(self, username):
        self._openshift_delete_user(username)
        self._openshift_delete_identity(username)
        logger.info(f"User {username} successfully deleted")

    def get_users(self, project_id):
        """Get all users with roles in a project"""
        users = set()

        # Check all standard OpenShift roles
        for role in OPENSHIFT_ROLES:
            try:
                rolebinding = self._openshift_get_rolebindings(project_id, role)
                if "subjects" in rolebinding:
                    users.update(
                        subject["name"]
                        for subject in rolebinding["subjects"]
                        if subject.get("kind") == "User"
                    )
            except kexc.NotFoundError:
                continue

        return users

    def _openshift_get_user(self, username):
        api = self.get_resource_api(API_USER, "User")
        return clean_openshift_metadata(api.get(name=username).to_dict())

    def _openshift_create_user(self, user_def):
        api = self.get_resource_api(API_USER, "User")
        try:
            return clean_openshift_metadata(api.create(body=user_def).to_dict())
        except kexc.ConflictError:
            pass

    def _openshift_delete_user(self, username):
        api = self.get_resource_api(API_USER, "User")
        return clean_openshift_metadata(api.delete(name=username).to_dict())

    def _openshift_get_identity(self, id_user):
        api = self.get_resource_api(API_USER, "Identity")
        return clean_openshift_metadata(
            api.get(name=self.qualified_id_user(id_user)).to_dict()
        )

    def _openshift_create_identity(self, identity_def):
        api = self.get_resource_api(API_USER, "Identity")
        try:
            return clean_openshift_metadata(api.create(body=identity_def).to_dict())
        except kexc.ConflictError:
            pass

    def _openshift_delete_identity(self, username):
        api = self.get_resource_api(API_USER, "Identity")
        return api.delete(name=self.qualified_id_user(username)).to_dict()

    def _openshift_create_useridentitymapping(self, identity_mapping_def):
        api = self.get_resource_api(API_USER, "UserIdentityMapping")
        try:
            return clean_openshift_metadata(
                api.create(body=identity_mapping_def).to_dict()
            )
        except kexc.ConflictError:
            pass

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

    def _openshift_delete_limits(self, project_name):
        api = self.get_resource_api(API_CORE, "LimitRange")

        limit_ranges = self._openshift_get_limits(project_name)
        for lr in limit_ranges["items"]:
            api.delete(namespace=project_name, name=lr["metadata"]["name"])

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

        if (
            resource_quota["spec"].get("hard")
            and "resourcequotas" in resource_quota["spec"]["hard"]
        ):
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

    def _user_in_rolebinding(self, username, rolebinding):
        """Check if a user is in a rolebinding"""
        if "subjects" not in rolebinding:
            return False

        return any(
            subject.get("kind") == "User" and subject.get("name") == username
            for subject in rolebinding["subjects"]
        )

    def _openshift_get_rolebindings(self, project_name, role):
        api = self.get_resource_api(API_RBAC, "RoleBinding")
        result = clean_openshift_metadata(
            api.get(namespace=project_name, name=role).to_dict()
        )

        # Ensure subjects is a list
        if not result.get("subjects"):
            result["subjects"] = []

        return result

    def _openshift_create_rolebindings(self, project_name, username, role):
        api = self.get_resource_api(API_RBAC, "RoleBinding")
        payload = {
            "metadata": {"name": role, "namespace": project_name},
            "subjects": [{"name": username, "kind": "User"}],
            "roleRef": {"name": role, "kind": "ClusterRole"},
        }
        return clean_openshift_metadata(
            api.create(body=payload, namespace=project_name).to_dict()
        )

    def _openshift_update_rolebindings(self, project_name, rolebinding):
        api = self.get_resource_api(API_RBAC, "RoleBinding")
        return clean_openshift_metadata(
            api.patch(body=rolebinding, namespace=project_name).to_dict()
        )

    def _openshift_list_rolebindings(self, project_name):
        """List all rolebindings in a project"""
        api = self.get_resource_api(API_RBAC, "RoleBinding")
        try:
            result = clean_openshift_metadata(api.get(namespace=project_name).to_dict())
            return result.get("items", [])
        except kexc.NotFoundError:
            return []
