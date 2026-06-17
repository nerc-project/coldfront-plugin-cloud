import os
import functools
import logging
from string import Template


import requests
from pydantic import BaseModel, ConfigDict, RootModel

from coldfront_plugin_cloud import base, attributes


logger = logging.getLogger(__name__)


def _clean_template_string(template_string: str) -> str:
    return template_string.replace(" ", "_").lower()


class MissingKeycloakTemplateError(Exception):
    pass


class KeyCloakGroup(BaseModel):
    """Keycloak group response model"""

    model_config = ConfigDict(extra="allow")
    id: str
    name: str


class GroupResponse(RootModel):
    """Wrapper for group list responses"""

    root: list[KeyCloakGroup]


class KeyCloakUser(BaseModel):
    """Keycloak user response model"""

    model_config = ConfigDict(extra="allow")
    id: str
    username: str


class UserResponse(RootModel):
    """Wrapper for user list responses"""

    root: list[KeyCloakUser]


class KeyCloakResourceAllocator(base.ResourceAllocator):
    def __init__(self, resource, allocation):
        self.resource = resource
        self.allocation = allocation

        self.base_url = os.getenv("KEYCLOAK_BASE_URL")
        self.realm = os.getenv("KEYCLOAK_REALM")
        self.client_id = os.getenv("KEYCLOAK_CLIENT_ID")
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")

        self.token_url = (
            f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token"
        )

    @functools.cached_property
    def group_name_template(self) -> str | None:
        return self.resource.get_attribute(attributes.RESOURCE_KEYCLOAK_GROUP_TEMPLATE)

    @functools.cached_property
    def group_name(self):
        """
        Acceptable variables for the group name template string is:
        - $resource_name: the name of the resource (e.g. "OpenShift")
        - Any allocation attribute defined for the allocation, with spaces replaced by underscores and
        all lowercase (e.g. for `Project Name`, the variable would be `$project_name`)
        """
        if self.group_name_template is None:
            raise MissingKeycloakTemplateError(
                f"Keycloak enabled but no group name template specified for resource {self.resource.name}"
            )

        resource_name = self.resource.name
        allocation_attrs_list = self.allocation.allocationattribute_set.all()

        template_sub_dict = {"resource_name": resource_name}
        for attr in allocation_attrs_list:
            template_sub_dict[
                _clean_template_string(attr.allocation_attribute_type.name)
            ] = attr.value

        return Template(self.group_name_template).substitute(**template_sub_dict)

    @functools.cached_property
    def api_client(self):
        params = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        r = requests.post(self.token_url, data=params)
        r.raise_for_status()
        headers = {
            "Authorization": ("Bearer %s" % r.json()["access_token"]),
            "Content-Type": "application/json",
        }
        session = requests.session()
        session.headers.update(headers)
        return session

    def create_federated_user(self, cf_username):
        """For testing purposes"""
        url = f"{self.base_url}/admin/realms/{self.realm}/users"
        payload = {
            "username": cf_username,
            "enabled": True,
            "email": cf_username,
        }
        r = self.api_client.post(url, json=payload)
        r.raise_for_status()

    def create_group(self, group_name):
        url = f"{self.base_url}/admin/realms/{self.realm}/groups"
        payload = {"name": group_name}
        response = self.api_client.post(url, json=payload)

        # If group already exists, ignore and move on
        if response.status_code not in (201, 409):
            response.raise_for_status()

    def get_group_id(self, group_name) -> str | None:
        """Return None if group not found"""
        query = {
            "search": group_name,
            "exact": "true",
        }
        url = f"{self.base_url}/admin/realms/{self.realm}/groups"
        r = self.api_client.get(url, params=query)
        r.raise_for_status()
        groups = GroupResponse.model_validate(r.json())
        return groups.root[0].id if groups.root else None

    def get_user_id(self, cf_username) -> str | None:
        """Return None if user not found"""
        # (Quan) Coldfront usernames map to Keycloak usernames
        # https://github.com/nerc-project/coldfront-plugin-cloud/pull/249#discussion_r2953393852
        query = {"username": cf_username, "exact": "true"}
        url = f"{self.base_url}/admin/realms/{self.realm}/users"
        r = self.api_client.get(url, params=query)
        r.raise_for_status()
        users = UserResponse.model_validate(r.json())
        return users.root[0].id if users.root else None

    def add_user_to_group(self, user_id, group_id):
        url = f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/groups/{group_id}"
        r = self.api_client.put(url)
        r.raise_for_status()

    def remove_user_from_group(self, user_id, group_id):
        url = f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/groups/{group_id}"
        r = self.api_client.delete(url)
        r.raise_for_status()

    def get_user_groups(self, user_id) -> list[str]:
        url = f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/groups"
        r = self.api_client.get(url)
        r.raise_for_status()
        groups = GroupResponse.model_validate(r.json())
        return [group.name for group in groups.root]

    def get_group_members(self, group_id) -> list[str]:
        url = f"{self.base_url}/admin/realms/{self.realm}/groups/{group_id}/members"
        page_size = 100  # Default KeyCloak page size https://www.keycloak.org/docs-api/latest/rest-api/index.html#_query_parameters_32
        page_offset = 0
        users = []

        while True:
            r = self.api_client.get(
                url, params={"first": page_offset, "max": page_size}
            )
            r.raise_for_status()
            batch = UserResponse.model_validate(r.json())
            users.extend(user.username for user in batch.root)
            if len(batch.root) < page_size:
                break
            page_offset += page_size

        return users

    def get_users(self, group_name) -> list[str]:
        """Returns list of usernames (not uuids) belonging to group 'group_name'
        If group hasn't been made yet, returns empty list"""
        group_id = self.get_group_id(group_name)
        return [] if group_id is None else self.get_group_members(group_id)

    def get_or_create_federated_user(self, username):
        """Only returns uuid for username. If user not found in Keycloak, they should not be created"""
        return self.get_user_id(username)

    def assign_role_on_user(self, username, group_name):
        if (user_id := self.get_user_id(username)) is None:
            logger.warning(
                f"User {username} not found in Keycloak, cannot add to group."
            )
            return

        self.create_group(group_name)
        group_id = self.get_group_id(group_name)
        self.add_user_to_group(user_id, group_id)
        logger.info(f"User {username} added to Keycloak group {group_name}")

    def remove_role_from_user(self, username, group_name):
        if (user_id := self.get_user_id(username)) is None:
            logger.warning(
                f"User {username} not found in Keycloak, cannot remove from group."
            )
            return

        if (group_id := self.get_group_id(group_name)) is None:
            logger.warning(
                f"Group {group_name} not found in Keycloak, skipping removal for user {username}."
            )
            return
        self.remove_user_from_group(user_id, group_id)
        logger.info(f"User {username} removed from Keycloak group {group_name}")

    def set_project_configuration(self, project_id, apply=True):
        raise NotImplementedError

    def get_project(self, project_id):
        raise NotImplementedError

    def create_project(self, suggested_project_name):
        raise NotImplementedError

    def disable_project(self, project_id):
        raise NotImplementedError

    def reactivate_project(self, project_id):
        raise NotImplementedError

    def create_project_defaults(self, project_id):
        raise NotImplementedError

    def set_quota(self, project_id):
        raise NotImplementedError

    def get_quota(self, project_id):
        raise NotImplementedError

    def get_federated_user(self, unique_id):
        raise NotImplementedError
