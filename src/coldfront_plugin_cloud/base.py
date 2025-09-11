import abc
import functools
import logging
from typing import NamedTuple

from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models

from coldfront_plugin_cloud import attributes, tasks, utils


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

    def get_or_create_federated_user(self, username):
        if not (user := self.get_federated_user(username)):
            user = self.create_federated_user(username)
        return user

    def set_default_quota_on_allocation(self, coldfront_attr):
        uqm = tasks.UNIT_QUOTA_MULTIPLIERS[self.resource_type]
        value = self.allocation.quantity * uqm.get(coldfront_attr, 0)
        value += tasks.STATIC_QUOTA[self.resource_type].get(coldfront_attr, 0)
        utils.set_attribute_on_allocation(self.allocation, coldfront_attr, value)
        return value

    def set_users(self, project_id, apply):
        coldfront_users = allocation_models.AllocationUser.objects.filter(
            allocation=self.allocation, status__name="Active"
        )
        allocation_users = self.get_users(project_id)
        failed_validation = False

        # Create users that exist in coldfront but not in the resource
        for coldfront_user in coldfront_users:
            if coldfront_user.user.username not in allocation_users:
                failed_validation = True
                logger.info(
                    f"{coldfront_user.user.username} is not part of {project_id}"
                )
                if apply:
                    tasks.add_user_to_allocation(coldfront_user.pk)

        # remove users that are in the resource but not in coldfront
        users = set(
            [coldfront_user.user.username for coldfront_user in coldfront_users]
        )
        for allocation_user in allocation_users:
            if allocation_user not in users:
                failed_validation = True
                logger.info(
                    f"{allocation_user} exists in the resource {project_id} but not in coldfront"
                )
                if apply:
                    self.remove_role_from_user(allocation_user, project_id)

        return failed_validation

    def check_and_apply_quota_attr(
        self, project_id, attr, expected_quota, current_quota, apply
    ):
        if current_quota is None and expected_quota is None:
            msg = (
                f"Value for quota for {attr} is not set anywhere"
                f" on {self.allocation_str}"
            )

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
                expected_quota = (
                    current_quota  # To pass `current_quota != expected_quota` check
                )
                msg = f"{msg} Attribute set to match current quota."
            logger.info(msg)

        if current_quota != expected_quota:
            msg = (
                f"Value for quota for {attr} = {current_quota} does not match expected"
                f" value of {expected_quota} on {self.allocation_str}"
            )
            logger.info(msg)

            if apply:
                try:
                    self.set_quota(project_id)
                    logger.info(f"Quota for {project_id} was out of date. Reapplied!")
                except Exception as e:
                    logger.info(f"setting openshift quota failed: {e}")
                    return

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
