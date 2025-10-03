import abc
import functools
from typing import NamedTuple
import logging

from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models

from coldfront_plugin_cloud import attributes, kc_client

logger = logging.getLogger(__name__)


class ResourceAllocator(abc.ABC):
    resource_type = ""

    project_name_max_length = None

    class Project(NamedTuple):
        name: str
        id: str

    def __init__(
        self,
        resource: resource_models.Resource,
        allocation: allocation_models.Allocation,
    ):
        self.resource = resource
        self.allocation = allocation

    @functools.cached_property
    def kc_admin_client(self):
        return kc_client.KeyCloakAPIClient()

    def get_or_create_federated_user(self, username):
        if not (user := self.get_federated_user(username)):
            user = self.create_federated_user(username)
        return user

    def assign_role_on_user(self, username, project_id):
        self.kc_admin_client.create_group(project_id)
        if user_id := self.kc_admin_client.get_user_id(username):
            group_id = self.kc_admin_client.get_group_id(project_id)
            self.kc_admin_client.add_user_to_group(user_id, group_id)
        else:
            logger.warning(
                f"User {username} not found in Keycloak, cannot add to group."
            )

    def remove_role_from_user(self, username, project_id):
        user_id = self.kc_admin_client.get_user_id(username)
        group_id = self.kc_admin_client.get_group_id(project_id)
        self.kc_admin_client.remove_user_from_group(user_id, group_id)

    @functools.cached_property
    def auth_url(self):
        return self.resource.get_attribute(attributes.RESOURCE_AUTH_URL).rstrip("/")

    @functools.cached_property
    def member_role_name(self):
        return self.resource.get_attribute(attributes.RESOURCE_ROLE) or "member"

    @abc.abstractmethod
    def create_project(self, suggested_project_name) -> Project:
        pass

    @abc.abstractmethod
    def disable_project(self, project_id):
        pass

    @abc.abstractmethod
    def reactivate_project(self, project_id):
        pass

    @abc.abstractmethod
    def create_project_defaults(self, project_id):
        pass

    @abc.abstractmethod
    def set_quota(self, project_id):
        pass

    @abc.abstractmethod
    def get_quota(self, project_id):
        pass

    @abc.abstractmethod
    def create_federated_user(self, unique_id):
        pass

    @abc.abstractmethod
    def get_federated_user(self, unique_id):
        pass
