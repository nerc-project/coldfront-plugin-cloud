from unittest import mock

from coldfront.core.allocation.models import Allocation

from coldfront_plugin_openstack import tasks
from coldfront_plugin_openstack.tests import base


class TestAllocation(base.TestBase):

    def test_allocation(self):
        openstack_resource = self.new_resource()
        project = self.new_project()
        allocation = self.new_allocation(project, openstack_resource, 2)


        tasks.activate_allocation(allocation.pk)
