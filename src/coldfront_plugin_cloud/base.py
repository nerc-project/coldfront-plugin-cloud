import abc
import functools
import json
from typing import NamedTuple

from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud.models.quota_models import QuotaSpecs


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

        resource_storage_classes_attr = resource_models.ResourceAttribute.objects.get(
            resource=resource,
            resource_attribute_type__name=attributes.RESOURCE_QUOTA_RESOURCES,
        )
        self.resource_quotaspecs = QuotaSpecs.model_validate(
            json.loads(resource_storage_classes_attr.value)
        )

    def get_or_create_federated_user(self, username):
        if not (user := self.get_federated_user(username)):
            user = self.create_federated_user(username)
        return user

    @functools.cached_property
    def auth_url(self):
        return self.resource.get_attribute(attributes.RESOURCE_AUTH_URL).rstrip("/")

    @functools.cached_property
    def member_role_name(self):
        return self.resource.get_attribute(attributes.RESOURCE_ROLE) or "member"

    @abc.abstractmethod
    def set_project_configuration(self, project_id, dry_run=False):
        pass

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

    @abc.abstractmethod
    def assign_role_on_user(self, username, project_id):
        pass

    @abc.abstractmethod
    def remove_role_from_user(self, username, project_id):
        pass
