import abc

from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models


class ResourceAllocator(abc.ABC):

    resource_type = ''

    def __init__(self,
                 resource: resource_models.Resource,
                 allocation: allocation_models.Allocation):
        self.resource = resource
        self.allocation = allocation

    def get_or_create_federated_user(self, username):
        if not (user := self.get_federated_user(username)):
            user = self.create_federated_user(username)
        return user

    @abc.abstractmethod
    def create_project(self, project_name) -> str:
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
