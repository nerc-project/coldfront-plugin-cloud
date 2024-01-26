"""Flask application for MOC openshift account management microservice"""

import os

from flask import Flask, make_response, request
from flask_httpauth import HTTPBasicAuth

import kubernetes.config
import kubernetes.client
import kubernetes.dynamic.exceptions as kexc
from openshift.dynamic import DynamicClient

from . import defaults
from . import moc_openshift
from . import exceptions

ENVPREFIX = "ACCT_MGT_"


def env_config():
    """Get configuration values from environment variables.

    Look up all environment variables that start with ENVPREFIX (by default
    "ACCT_MGT_"), strip the prefix, and store them in a dictionary. Return the
    dictionary to the caller.
    """

    return {
        k[len(ENVPREFIX) :]: v for k, v in os.environ.items() if k.startswith(ENVPREFIX)
    }


def get_dynamic_client(logger):
    try:
        k8s_client = kubernetes.config.new_client_from_config()
        logger.info("using kubeconfig credentials")
    except kubernetes.config.config_exception.ConfigException:
        kubernetes.config.load_incluster_config()
        k8s_client = kubernetes.client.ApiClient()
        logger.info("using in-cluster credentials")
    return DynamicClient(k8s_client)


def get_openshift(client, logger, config):
    return moc_openshift.MocOpenShift4x(client, logger, config)


# pylint: disable=too-many-statements,too-many-locals,redefined-outer-name
def create_app(**config):
    APP = Flask(__name__)
    AUTH = HTTPBasicAuth()

    APP.config.from_object(defaults)
    APP.config.from_mapping(config)

    # Allow unit tests to explicitly disable environment configuration
    if not APP.config.get("DISABLE_ENV_CONFIG", False):
        APP.config.from_mapping(env_config())

    dyn_client = get_dynamic_client(APP.logger)
    shift = get_openshift(dyn_client, APP.logger, APP.config)

    @AUTH.verify_password
    def verify_password(username, password):
        """Validates a username and password."""

        return (
            APP.config.get("AUTH_DISABLED", "false").lower()
            in ("true", "t", "yes", "1")
        ) or (
            username == APP.config["ADMIN_USERNAME"]
            and password == APP.config["ADMIN_PASSWORD"]
        )

    @APP.errorhandler(exceptions.ApiException)
    def handle_acct_mgt_errors(error):
        msg = error.message if error.visible else "Internal Server Error"
        APP.logger.error(msg)
        return make_response({"msg": msg}, error.status_code)

    @APP.errorhandler(kexc.DynamicApiError)
    def handle_openshift_api_errors(error):
        msg = f"Unexpected response from OpenShift API: {error.summary()}"
        APP.logger.error(msg)
        return make_response({"msg": msg}, 400)

    @APP.errorhandler(ValueError)
    def handle_value_errors(error):
        msg = f"Invalid value in input: {error}"
        APP.logger.error(msg)
        return make_response({"msg": msg}, 400)

    @APP.route(
        "/users/<user_name>/projects/<project_name>/roles/<role>", methods=["GET"]
    )
    @AUTH.login_required
    def get_moc_rolebindings(project_name, user_name, role):
        # role can be one of admin, edit, view
        if shift.user_rolebinding_exists(user_name, project_name, role):
            return {"msg": f"user role exists ({project_name},{user_name},{role})"}

        return make_response(
            {"msg": f"user role does not exist ({project_name},{user_name},{role})"},
            404,
        )

    @APP.route(
        "/users/<user_name>/projects/<project_name>/roles/<role>", methods=["PUT"]
    )
    @AUTH.login_required
    def create_moc_rolebindings(project_name, user_name, role):
        # role can be one of admin, edit, view
        return shift.add_user_to_role(project_name, user_name, role)

    @APP.route(
        "/users/<user_name>/projects/<project_name>/roles/<role>", methods=["DELETE"]
    )
    @AUTH.login_required
    def delete_moc_rolebindings(project_name, user_name, role):
        # role can be one of admin, edit, view
        return shift.remove_user_from_role(project_name, user_name, role)

    @APP.route("/projects/<project_name>", methods=["GET"])
    @AUTH.login_required
    def get_moc_project(project_name):
        if shift.project_exists(project_name):
            return make_response(
                {"msg": f"project exists ({project_name})"},
            )
        return make_response({"msg": f"project does not exist ({project_name})"}, 400)

    @APP.route("/projects/<project_name>", methods=["PUT"])
    @APP.route("/projects/<project_name>/owner/<user_name>", methods=["PUT"])
    @AUTH.login_required
    def create_moc_project(project_name, user_name=None):
        # first check the project_name is a valid openshift project name
        suggested_project_name = shift.cnvt_project_name(project_name)
        if project_name != suggested_project_name:
            raise exceptions.BadRequest(
                "project name must match regex '[a-z0-9]([-a-z0-9]*[a-z0-9])?'."
                f" Suggested name: {suggested_project_name}."
            )

        if shift.project_exists(project_name):
            raise exceptions.Conflict("project already exists.")

        payload = request.get_json(silent=True) or {}
        display_name = payload.pop("displayName", project_name)
        annotations = payload.pop("annotations", {})
        labels = payload.pop("labels", {})

        shift.create_project(
            project_name,
            display_name,
            user_name,
            annotations=annotations,
            labels=labels,
        )
        return {"msg": f"project created ({project_name})"}

    @APP.route("/projects/<project_name>", methods=["DELETE"])
    @AUTH.login_required
    def delete_moc_project(project_name):
        if shift.project_exists(project_name):
            shift.delete_project(project_name)

        return make_response({"msg": f"project deleted ({project_name})"})

    @APP.route("/users/<user_name>", methods=["GET"])
    @AUTH.login_required
    def get_moc_user(user_name):
        if shift.user_exists(user_name):
            return make_response({"msg": f"user ({user_name}) exists"})
        return make_response({"msg": f"user ({user_name}) does not exist"}, 404)

    @APP.route("/users/<user_name>", methods=["PUT"])
    @AUTH.login_required
    def create_moc_user(user_name):
        # these three values should be added to generalize this function
        # full_name    - the full name of the user as it is really convenient
        # id_provider  - this is in the yaml configuration for this project - needed in the past

        full_name = user_name
        id_user = user_name  # until we support different user names see above.

        created = False

        if not shift.user_exists(user_name):
            created = True
            shift.create_user(user_name, full_name)

        if not shift.identity_exists(id_user):
            created = True
            shift.create_identity(id_user)

        if not shift.useridentitymapping_exists(user_name, id_user):
            created = True
            shift.create_useridentitymapping(user_name, id_user)

        if created:
            return make_response({"msg": f"user created ({user_name})"})
        return make_response({"msg": f"user already exists ({user_name})"}, 400)

    @APP.route("/users/<user_name>", methods=["DELETE"])
    @AUTH.login_required
    def delete_moc_user(user_name):
        if shift.user_exists(user_name):
            shift.delete_user(user_name)

        if shift.identity_exists(user_name):
            shift.delete_identity(user_name)

        return make_response({"msg": f"user deleted ({user_name})"})

    @APP.route("/projects/<project>/quota", methods=["GET"])
    @AUTH.login_required
    def get_quota(project):
        return shift.get_moc_quota(project)

    @APP.route("/projects/<project>/quota", methods=["PUT", "POST"])
    @AUTH.login_required
    def put_quota(project):
        moc_quota = request.get_json(force=True)
        return shift.update_moc_quota(project, moc_quota, patch=False)

    @APP.route("/projects/<project>/quota", methods=["PATCH"])
    @AUTH.login_required
    def patch_quota(project):
        moc_quota = request.get_json(force=True)
        return shift.update_moc_quota(project, moc_quota, patch=True)

    @APP.route("/projects/<project>/quota", methods=["DELETE"])
    @AUTH.login_required
    def delete_quota(project):
        return shift.delete_moc_quota(project)

    @APP.route("/projects/<project>/users", methods=["GET"])
    @AUTH.login_required
    def get_users_in_project(project):
        return shift.get_users_in_project(project)

    return APP
