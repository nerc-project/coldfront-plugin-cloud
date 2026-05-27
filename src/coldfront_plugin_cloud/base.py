import abc
import functools
import json
import logging
from typing import NamedTuple

from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models

from coldfront_plugin_cloud import attributes, utils
from coldfront_plugin_cloud.models.quota_models import QuotaSpecs


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

        try:
            resource_quota_attr = resource_models.ResourceAttribute.objects.get(
                resource=resource,
                resource_attribute_type__name=attributes.RESOURCE_QUOTA_RESOURCES,
            )
            self.resource_quotaspecs = QuotaSpecs.model_validate(
                json.loads(resource_quota_attr.value)
            )
        except resource_models.ResourceAttribute.DoesNotExist as e:
            raise ValueError(
                f"Resource {resource.name} does not have quota resources defined. Run either register_default_quotas or add_quota_to_resource management command to add quotas to the resource."
            ) from e

    def get_or_create_federated_user(self, username):
        if not (user := self.get_federated_user(username)):
            user = self.create_federated_user(username)
        return user

    def set_default_quota_on_allocation(self, coldfront_attr):
        resource_quotaspecs = self.resource_quotaspecs
        value = resource_quotaspecs.root[coldfront_attr].quota_by_su_quantity(
            self.allocation.quantity
        )
        utils.set_attribute_on_allocation(self.allocation, coldfront_attr, value)
        return value

    def set_users(self, project_id, apply):
        coldfront_users = allocation_models.AllocationUser.objects.filter(
            allocation=self.allocation, status__name="Active"
        )
        cluster_users = self.get_users(project_id)
        failed_validation = False

        # Create users that exist in coldfront but not in the resource
        for coldfront_user in coldfront_users:
            coldfront_username = coldfront_user.user.username
            if coldfront_username not in cluster_users:
                failed_validation = True
                logger.info(f"{coldfront_username} is not part of {project_id}")
                if apply:
                    self.get_or_create_federated_user(coldfront_username)
                    self.assign_role_on_user(coldfront_username, project_id)

        # remove users that are in the resource but not in coldfront
        users = set(
            [coldfront_user.user.username for coldfront_user in coldfront_users]
        )
        for allocation_user in cluster_users:
            if allocation_user not in users:
                failed_validation = True
                logger.info(
                    f"{allocation_user} exists in the resource {project_id} but not in coldfront"
                )
                if apply:
                    self.remove_role_from_user(allocation_user, project_id)

        return failed_validation

    def check_and_apply_quota_attr(
        self,
        attr: str,
        expected_quota: int | None,
        current_quota: int | None,
        apply: bool,
    ) -> bool:
        failed_validation = False
        if current_quota is None and expected_quota is None:
            msg = (
                f"Value for quota for {attr} is not set anywhere"
                f" on {self.allocation_str}"
            )
            failed_validation = True

            if apply:
                expected_quota = self.set_default_quota_on_allocation(attr)
                msg = f"Added default quota for {attr} to {self.allocation_str} to {expected_quota}"
            logger.info(msg)
        elif current_quota is not None and expected_quota is None:
            msg = (
                f'Attribute "{attr}" expected on {self.allocation_str} but not set.'
                f" Current quota is {current_quota}."
            )

            if apply:
                utils.set_attribute_on_allocation(self.allocation, attr, current_quota)

                # To pass `current_quota != expected_quota` check
                expected_quota = current_quota

                msg = f"{msg} Attribute set to match current quota."
            logger.info(msg)

        if current_quota != expected_quota:
            msg = (
                f"Value for quota for {attr} = {current_quota} does not match expected"
                f" value of {expected_quota} on {self.allocation_str}"
            )
            logger.info(msg)
            failed_validation = True

        return failed_validation

    @functools.cached_property
    def allocation_str(self):
        return f'allocation {self.allocation.pk} of project "{self.allocation.project.title}"'

    @functools.cached_property
    def auth_url(self):
        return self.resource.get_attribute(attributes.RESOURCE_AUTH_URL).rstrip("/")

    @functools.cached_property
    def member_role_name(self):
        return self.resource.get_attribute(attributes.RESOURCE_ROLE) or "member"

    @abc.abstractmethod
    def set_project_configuration(self, project_id, apply=True):
        pass

    @abc.abstractmethod
    def get_project(self, project_id):
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
    def get_users(self, unique_id):
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
