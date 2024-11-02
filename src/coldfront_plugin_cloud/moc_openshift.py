"""API wrapper for interacting with OpenShift authorization"""
import json
import re
import sys
import time

import kubernetes.dynamic.exceptions as kexc

OPENSHIFT_ROLES = ["admin", "edit", "view"]

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


# pylint: disable=too-many-public-methods
class MocOpenShift4x:
    """API implementation for OpenShift 4.x"""

    @staticmethod
    def split_quota_name(moc_quota_name):
        name_array = moc_quota_name.split(":")
        return name_array[0] or "Project", name_array[1]

    @staticmethod
    def cnvt_project_name(project_name):
        suggested_project_name = re.sub("^[^A-Za-z0-9]+", "", project_name.lower())
        suggested_project_name = re.sub("[^A-Za-z0-9]+$", "", suggested_project_name)
        suggested_project_name = re.sub("[^A-Za-z0-9-]+", "-", suggested_project_name)
        return suggested_project_name

    @staticmethod
    def user_in_rolebinding(user_name, rolebinding):
        return [
            subject
            for subject in rolebinding["subjects"]
            if subject["kind"] == "User" and subject["name"] == user_name
        ]

    @staticmethod
    def validate_role(role):
        if role not in OPENSHIFT_ROLES:
            raise ValueError(
                f"Invalid role, {role} is not one of {', '.join(OPENSHIFT_ROLES)}"
            )

    def __init__(self, client, logger, config):
        self.client = client
        self.logger = logger
        self.id_provider = config["IDENTITY_PROVIDER"]
        self.quotafile = config["QUOTA_DEF_FILE"]
        self.limitfile = config["LIMIT_DEF_FILE"]
        self.apis = {}

        if not self.limitfile:
            self.logger.error("No default limit file provided.")
            sys.exit(1)

    def get_resource_api(self, api_version: str, kind: str):
        """Either return the cached resource api from self.apis, or fetch a
        new one, store it in self.apis, and return it."""
        k = f"{api_version}:{kind}"
        api = self.apis.setdefault(
            k, self.client.resources.get(api_version=api_version, kind=kind)
        )
        return api

    def useridentitymapping_exists(self, user_name, id_user):
        try:
            user = self.get_user(user_name)
        except kexc.NotFoundError:
            return False

        return any(
            identity == self.qualified_id_user(id_user)
            for identity in user.get("identities", [])
        )

    def user_rolebinding_exists(self, user_name, project_name, role):
        self.validate_role(role)

        try:
            result = self.get_rolebindings(project_name, role)
        except kexc.NotFoundError:
            return False

        return any(
            (subject["kind"] == "User" and subject["name"] == user_name)
            for subject in result["subjects"]
        )

    def add_user_to_role(self, project_name, user_name, role):
        self.validate_role(role)

        try:
            rolebinding = self.get_rolebindings(project_name, role)

            if not self.user_in_rolebinding(user_name, rolebinding):
                rolebinding["subjects"].append({"kind": "User", "name": user_name})
                self.update_rolebindings(project_name, rolebinding)
        except kexc.NotFoundError:
            rolebinding = self.create_rolebindings(project_name, user_name, role)

        return {
            "msg": f"added user {user_name} to role {role} in {project_name}",
        }

    def remove_user_from_role(self, project_name, user_name, role):
        self.validate_role(role)

        try:
            rolebinding = self.get_rolebindings(project_name, role)

            for subject in self.user_in_rolebinding(user_name, rolebinding):
                rolebinding["subjects"].remove(subject)

            self.update_rolebindings(project_name, rolebinding)
        except kexc.NotFoundError:
            pass

        return {
            "msg": f"removed user {user_name} from role {role} in {project_name}",
        }

    def update_moc_quota(self, project_name, new_quota, patch=False):
        """This will update resourcequota objects in a project and create new
        ones based on the new_quota specification"""
        quota_def = self.get_quota_definitions()

        if patch:
            existing_quota = self.get_moc_quota_from_resourcequotas(project_name)
            for quota, value in existing_quota.items():
                quota_def.setdefault(quota, {})["value"] = value

        for quota, value in new_quota["Quota"].items():
            quota_def[quota]["value"] = value
        self.logger.info(
            f"New Quota for project {project_name}: {json.dumps(new_quota, indent=2)}"
        )

        self.delete_moc_quota(project_name)
        self.create_shift_quotas(project_name, quota_def)

        return {"msg": "MOC quotas updated"}

    def get_quota_definitions(self):
        self.logger.info("reading quotas from %s", self.quotafile)
        with open(self.quotafile, "r") as file:
            quota = json.load(file)
        for k in quota:
            quota[k]["value"] = None

        return quota

    def get_limit_definitions(self):
        with open(self.limitfile, "r") as file:
            return json.load(file)

    def get_project(self, project_name):
        api = self.get_resource_api(API_PROJECT, "Project")
        return clean_openshift_metadata(api.get(name=project_name).to_dict())

    def project_exists(self, project_name):
        try:
            self.get_project(project_name)
        except kexc.NotFoundError:
            return False
        return True

    # pylint: disable-msg=too-many-arguments
    def create_project(
        self, project_name, display_name, user_name, annotations=None, labels=None
    ):
        if annotations is None:
            annotations = {}
        else:
            annotations = dict(annotations)

        api = self.get_resource_api(API_PROJECT, "Project")

        annotations.update(
            {
                "openshift.io/display-name": display_name,
                "openshift.io/requester": user_name,
            }
        )

        _nerc_project_label = {
            "nerc.mghpcc.org/project": "true",
        }

        if labels is None:
            labels = _nerc_project_label
        else:
            labels = dict(labels)
            labels.update(_nerc_project_label)

        payload = {
            "metadata": {
                "name": project_name,
                "annotations": annotations,
                "labels": labels,
            },
        }
        res = api.create(body=payload).to_dict()
        self.create_limits(project_name)
        return res

    # pylint: enable-msg=too-many-arguments

    def delete_project(self, project_name):
        api = self.get_resource_api(API_PROJECT, "Project")
        return api.delete(name=project_name).to_dict()

    def get_user(self, user_name):
        api = self.get_resource_api(API_USER, "User")
        return clean_openshift_metadata(api.get(name=user_name).to_dict())

    def user_exists(self, user_name):
        try:
            self.get_user(user_name)
        except kexc.NotFoundError:
            return False
        return True

    def create_user(self, user_name, full_name):
        api = self.get_resource_api(API_USER, "User")
        payload = {
            "metadata": {"name": user_name},
            "fullName": full_name,
        }
        return api.create(body=payload).to_dict()

    def delete_user(self, user_name):
        api = self.get_resource_api(API_USER, "User")
        return api.delete(name=user_name).to_dict()

    def qualified_id_user(self, id_user):
        return f"{self.id_provider}:{id_user}"

    def get_identity(self, id_user):
        api = self.get_resource_api(API_USER, "Identity")
        return clean_openshift_metadata(
            api.get(name=self.qualified_id_user(id_user)).to_dict()
        )

    def identity_exists(self, id_user):
        try:
            self.get_identity(id_user)
        except kexc.NotFoundError:
            return False
        return True

    def create_identity(self, id_user):
        api = self.get_resource_api(API_USER, "Identity")

        payload = {
            "providerName": self.id_provider,
            "providerUserName": id_user,
        }
        return api.create(body=payload).to_dict()

    def delete_identity(self, id_user):
        api = self.get_resource_api(API_USER, "Identity")
        return api.delete(name=self.qualified_id_user(id_user)).to_dict()

    def create_useridentitymapping(self, user_name, id_user):
        api = self.get_resource_api(API_USER, "UserIdentityMapping")
        payload = {
            "user": {"name": user_name},
            "identity": {"name": self.qualified_id_user(id_user)},
        }
        return api.create(body=payload).to_dict()

    # member functions to associate roles for users on projects
    def get_rolebindings(self, project_name, role):
        api = self.get_resource_api(API_RBAC, "RoleBinding")
        res = clean_openshift_metadata(
            api.get(namespace=project_name, name=role).to_dict()
        )

        # Ensure that rbd["subjects"] is a list (it can be None if the
        # rolebinding object had no subjects).
        if not res.get("subjects"):
            res["subjects"] = []

        return res

    def list_rolebindings(self, project_name):
        api = self.get_resource_api(API_RBAC, "RoleBinding")
        try:
            res = clean_openshift_metadata(api.get(namespace=project_name).to_dict())
        except kexc.NotFoundError:
            return []

        return res["items"]

    def create_rolebindings(self, project_name, user_name, role):
        api = self.get_resource_api(API_RBAC, "RoleBinding")
        payload = {
            "metadata": {"name": role, "namespace": project_name},
            "subjects": [{"name": user_name, "kind": "User"}],
            "roleRef": {"name": role, "kind": "ClusterRole"},
        }
        return api.create(body=payload, namespace=project_name).to_dict()

    def update_rolebindings(self, project_name, rolebinding):
        api = self.get_resource_api(API_RBAC, "RoleBinding")
        return api.patch(body=rolebinding, namespace=project_name).to_dict()

    def get_moc_quota(self, project_name):
        quota_from_project = self.get_moc_quota_from_resourcequotas(project_name)

        quota = {}
        for quota_name, quota_value in quota_from_project.items():
            if quota_value:
                quota[quota_name] = quota_value

        quota_object = {
            "Version": "0.9",
            "Kind": "MocQuota",
            "ProjectName": project_name,
            "Quota": quota,
        }
        return quota_object

    def wait_for_quota_to_settle(self, project_name, resource_quota):
        """Wait for quota on resourcequotas to settle.

        When creating a new resourcequota that sets a quota on resourcequota objects, we need to
        wait for OpenShift to calculate the quota usage before we attempt to create any new
        resourcequota objects.
        """

        if "resourcequotas" in resource_quota["spec"]["hard"]:
            self.logger.info("waiting for resourcequota quota")

            api = self.get_resource_api(API_CORE, "ResourceQuota")
            while True:
                resp = clean_openshift_metadata(
                    api.get(
                        namespace=project_name, name=resource_quota["metadata"]["name"]
                    ).to_dict()
                )
                if "resourcequotas" in resp["status"].get("used", {}):
                    break
                time.sleep(0.1)

    def create_shift_quotas(self, project_name, quota_spec):
        quota_def = {}
        # separate the quota_spec by quota_scope
        for mangled_quota_name in quota_spec:
            (scope, quota_name) = self.split_quota_name(mangled_quota_name)
            quota_def.setdefault(scope, {})
            quota_def[scope][quota_name] = quota_spec[mangled_quota_name]

        for scope, quota_item in quota_def.items():
            resource_quota = {
                "metadata": {"name": f"{project_name.lower()}-{scope.lower()}"},
                "spec": {"hard": {}},
            }

            if scope != "Project":
                resource_quota["spec"]["scopes"] = [scope]

            resource_quota["spec"]["hard"] = {
                quota_name: quota_item[quota_name]["value"]
                for quota_name in quota_item
                if quota_item[quota_name]["value"] is not None
            }

            if resource_quota["spec"]["hard"]:
                api = self.get_resource_api(API_CORE, "ResourceQuota")
                res = api.create(namespace=project_name, body=resource_quota).to_dict()
                self.wait_for_quota_to_settle(project_name, res)

        return {"msg": f"All quotas for {project_name} successfully created"}

    def get_resourcequotas(self, project_name):
        """Returns a list of all of the resourcequota objects"""
        # Raise a NotFound error if the project doesn't exist
        self.get_project(project_name)

        api = self.get_resource_api(API_CORE, "ResourceQuota")
        res = clean_openshift_metadata(api.get(namespace=project_name).to_dict())

        return res["items"]

    def delete_resourcequota(self, project_name, resourcequota_name):
        """In an openshift namespace {project_name) delete a specified resourcequota"""
        api = self.get_resource_api(API_CORE, "ResourceQuota")
        return api.delete(namespace=project_name, name=resourcequota_name).to_dict()

    def delete_moc_quota(self, project_name):
        """deletes all resourcequotas from an openshift project"""
        resourcequotas = self.get_resourcequotas(project_name)
        for resourcequota in resourcequotas:
            self.delete_resourcequota(project_name, resourcequota["metadata"]["name"])

        return {"msg": f"All quotas for {project_name} successfully deleted"}

    def get_moc_quota_from_resourcequotas(self, project_name):
        """This returns a dictionary suitable for merging in with the
        specification from Adjutant/ColdFront"""
        resourcequotas = self.get_resourcequotas(project_name)
        moc_quota = {}
        for rq in resourcequotas:
            name, spec = rq["metadata"]["name"], rq["spec"]
            self.logger.info(f"processing resourcequota: {project_name}:{name}")
            scope_list = spec.get("scopes", [""])
            for quota_name, quota_value in spec.get("hard", {}).items():
                for scope_item in scope_list:
                    moc_quota_name = f"{scope_item}:{quota_name}"
                    moc_quota.setdefault(moc_quota_name, quota_value)
        return moc_quota

    def create_limits(self, project_name, limits=None):
        """
        project_name: project_name in which to create LimitRange
        limits: dictionary of limits to create, or None for default
        """
        api = self.get_resource_api(API_CORE, "LimitRange")

        payload = {
            "metadata": {"name": f"{project_name.lower()}-limits"},
            "spec": {"limits": limits or self.get_limit_definitions()},
        }
        return api.create(body=payload, namespace=project_name).to_dict()

    def get_users_in_project(self, project_name):
        """
        Returns a list of users that have a role in a given project/namespace
        """
        # Raise a NotFound error if the project doesn't exist
        self.get_project(project_name)

        users = set()
        role_binding_list = []

        for role in OPENSHIFT_ROLES:
            try:
                role_binding_list.append(self.get_rolebindings(project_name, role))
            except kexc.NotFoundError:
                continue

        for role_binding in role_binding_list:
            users.update(
                subject["name"]
                for subject in role_binding["subjects"]
                if subject["kind"] == "User"
            )

        return list(users)
