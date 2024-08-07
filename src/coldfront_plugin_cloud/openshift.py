import logging
import os

import kubernetes.config
import kubernetes.client
import kubernetes.dynamic.exceptions as kexc
from openshift.dynamic import DynamicClient
from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models

from coldfront_plugin_cloud.acct_mgt import moc_openshift
from coldfront_plugin_cloud import attributes, base, utils

QUOTA_OPENSHIFT = {
    ":requests.cpu": {"base": 2, "coefficient": 0},
    ":requests.memory": {"base": 2, "coefficient": 0},
    ":limits.cpu": {"base": 2, "coefficient": 0},
    ":limits.memory": {"base": 2, "coefficient": 0},
    ":requests.storage": {"base": 2, "coefficient": 0, "units": "Gi"},
    ":limits.storage": {"base": 2, "coefficient": 0, "units": "Gi"},
    ":requests.ephemeral-storage": {"base": 2, "coefficient": 8, "units": "Gi"},
    ":requests.nvidia.com/gpu": {"base": 0, "coefficient": 0},
    ":limits.ephemeral-storage": {"base": 2, "coefficient": 8, "units": "Gi"},
    ":persistentvolumeclaims": {"base": 2, "coefficient": 0},
    ":replicationcontrollers": {"base": 2, "coefficient": 0},
    ":resourcequotas": {"base": 5, "coefficient": 0},
    ":services": {"base": 4, "coefficient": 0},
    ":services.loadbalancers": {"base": 2, "coefficient": 0},
    ":services.nodeports": {"base": 2, "coefficient": 0},
    ":secrets": {"base": 4, "coefficient": 0},
    ":configmaps": {"base": 4, "coefficient": 0},
    ":openshift.io/imagestreams": {"base": 2, "coefficient": 0},
    "BestEffort:pods": {"base": 2, "coefficient": 2},
    "NotBestEffort:pods": {"base": 2, "coefficient": 2},
    "NotBestEffort:requests.memory": {"base": 2, "coefficient": 4, "units": "Gi"},
    "NotBestEffort:limits.memory": {"base": 2, "coefficient": 4, "units": "Gi"},
    "NotBestEffort:requests.cpu": {"base": 2, "coefficient": 2},
    "NotBestEffort:limits.cpu": {"base": 2, "coefficient": 2},
    "Terminating:pods": {"base": 2, "coefficient": 2},
    "Terminating:requests.memory": {"base": 2, "coefficient": 4, "units": "Gi"},
    "Terminating:limits.memory": {"base": 2, "coefficient": 4, "units": "Gi"},
    "Terminating:requests.cpu": {"base": 2, "coefficient": 2},
    "Terminating:limits.cpu": {"base": 2, "coefficient": 2},
    "NotTerminating:pods": {"base": 2, "coefficient": 2},
    "NotTerminating:requests.memory": {"base": 2, "coefficient": 4, "units": "Gi"},
    "NotTerminating:limits.memory": {"base": 2, "coefficient": 4, "units": "Gi"},
    "NotTerminating:requests.cpu": {"base": 2, "coefficient": 2},
    "NotTerminating:limits.cpu": {"base": 2, "coefficient": 2},
}

LIMITS_OPENSHIFT = [
    {
        "type": "Container",
        "default": {"cpu": "2", "memory": "1024Mi", "nvidia.com/gpu": "0"},
        "defaultRequest": {"cpu": "1", "memory": "512Mi", "nvidia.com/gpu": "0"},
    }
]

QUOTA_KEY_MAPPING = {
    attributes.QUOTA_LIMITS_CPU: lambda x: {":limits.cpu": f"{x * 1000}m"},
    attributes.QUOTA_LIMITS_MEMORY: lambda x: {":limits.memory": f"{x}Mi"},
    attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: lambda x: {
        ":limits.ephemeral-storage": f"{x}Gi"
    },
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
    resource_type = "openshift"

    project_name_max_length = 63

    def __init__(
        self,
        resource: resource_models.Resource,
        allocation: allocation_models.Allocation,
    ):
        super().__init__(resource, allocation)

        # Load Endpoint URL and Auth token for new k8 client
        var_name = utils.env_safe_name(self.resource.name)
        openshift_token = os.getenv(f"OPENSHIFT_{var_name}_TOKEN")
        openshift_url = resource.get_attribute(attributes.RESOURCE_AUTH_URL)
        identity_name = resource.get_attribute(attributes.RESOURCE_IDENTITY_NAME)

        functional_tests = os.environ.get("FUNCTIONAL_TESTS", "").lower()
        verify = os.getenv(f"OPENSHIFT_{var_name}_VERIFY", "").lower()

        k8_config = kubernetes.client.Configuration()
        k8_config.api_key["authorization"] = openshift_token
        k8_config.api_key_prefix["authorization"] = "Bearer"
        k8_config.host = openshift_url

        if functional_tests == "true" or verify == "false":
            self.logger = logging.getLogger()
            logger = logging.getLogger()
            k8_config.verify_ssl = False
        else:
            self.logger = logging.getLogger("django")
            logger = logging.getLogger("django")
            k8_config.verify_ssl = True

        k8s_client = kubernetes.client.ApiClient(configuration=k8_config)

        self.client = moc_openshift.MocOpenShift4x(
            DynamicClient(k8s_client), logger, identity_name, QUOTA_OPENSHIFT, LIMITS_OPENSHIFT
        )

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

    def set_quota(self, project_id):
        payload = dict()
        for key, func in QUOTA_KEY_MAPPING.items():
            if (x := self.allocation.get_attribute(key)) is not None:
                payload.update(func(x))

        return self.client.update_moc_quota(project_id, {"Quota": payload}, patch=False)

    def get_quota(self, project_id):
        return self.client.get_moc_quota(project_id)

    def create_project_defaults(self, project_id):
        pass

    def disable_project(self, project_id):
        if self.client.project_exists(project_id):
            self.client.delete_project(project_id)

    def reactivate_project(self, project_id):
        project_name = self.allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME)
        self._create_project(project_name, project_id)

    def get_federated_user(self, username):
        if self.client.user_exists(username) and self.client.identity_exists(
            username) and self.client.useridentitymapping_exists(username, username):
            return {"username": username}

        self.logger.info("404: " + f"user ({username}) does not exist")

    def create_federated_user(self, unique_id):
        try:
            full_name = unique_id
            id_user = unique_id  # until we support different user names see above.

            created = False

            if not self.client.user_exists(unique_id):
                created = True
                self.client.create_user(unique_id, full_name)

            if not self.client.identity_exists(id_user):
                created = True
                self.client.create_identity(id_user)

            if not self.client.useridentitymapping_exists(unique_id, id_user):
                created = True
                self.client.create_useridentitymapping(unique_id, id_user)

            if created:
                self.logger.info(f"msg: user created ({unique_id})")
                return

        except Exception:
            pass

    def assign_role_on_user(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>
        try:
            return self.client.add_user_to_role(
                project_id, username, self.member_role_name
            )
        except Conflict:
            pass

    def remove_role_from_user(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>

        return self.client.remove_user_from_role(
            project_id, username, self.member_role_name
        )

    def _create_project(self, project_name, project_id):
        suggested_project_name = self.client.cnvt_project_name(project_name)
        if project_name != suggested_project_name:
            self.logger.info("400: " +
                "project name must match regex '[a-z0-9]([-a-z0-9]*[a-z0-9])?'." +
                f" Suggested name: {suggested_project_name}."
            )
            return

        if self.client.project_exists(project_name):
            self.logger.info("409: project already exists.")
            return

        display_name = project_name
        annotations = {
            "cf_project_id": str(self.allocation.project_id),
            "cf_pi": self.allocation.project.pi.username,
        }
        labels = {"opendatahub.io/dashboard": "true"}
        user_name = None

        self.client.create_project(
            project_name,
            display_name,
            user_name,
            annotations=annotations,
            labels=labels,
        )
        self.logger.info(f"msg: project created ({project_name})")

    def _get_role(self, username, project_id):
        # /users/<user_name>/projects/<project>/roles/<role>

        if self.client.user_rolebinding_exists(
            username, project_id, self.member_role_name
        ):
            self.logger.info(
                f"msg: user role exists ({project_id},{username},{self.member_role_name})"
            )
            return

        raise NotFound(
            "404: "
            + f"user role does not exist ({project_id},{username},{self.member_role_name})"
        )

    def _get_project(self, project_id):
        if self.client.project_exists(project_id):
            self.logger.info(f"msg: project exists ({project_id})")
            return

        raise NotFound("404: " + f"project does not exist ({project_id})")

    def _delete_user(self, username):
        if self.client.user_exists(username):
            self.client.delete_user(username)

        if self.client.identity_exists(username):
            self.client.delete_identity(username)

        return {"msg": f"user deleted ({username})"}

    def get_users(self, project_id):
        return set(self.client.get_users_in_project(project_id))
