import json
import uuid

from coldfront_plugin_cloud import attributes, utils
from coldfront_plugin_cloud.tests import base

from rest_framework.test import APIClient


class TestApiAllocations(base.TestBase):

    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_resource(name='Devstack',
                                          auth_url='http://example.com')

    def test_api(self):
        client = APIClient()

        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)

        allocated_project_id = uuid.uuid4().hex
        allocated_project_name = uuid.uuid4().hex
        utils.set_attribute_on_allocation(
            allocation, attributes.ALLOCATION_PROJECT_ID, allocated_project_id
        )
        utils.set_attribute_on_allocation(
            allocation, attributes.ALLOCATION_PROJECT_NAME, allocated_project_name
        )

        allocation.refresh_from_db()

        http_response = client.get('/cloud-api/allocations/')
        self.assertEqual(http_response.status_code, 200)
        self.assertGreaterEqual(len(json.loads(http_response.content)), 1)

        http_response = self.client.get(f'/cloud-api/allocations/{allocation.pk}/')
        self.assertEqual(http_response.status_code, 200)
        r = json.loads(http_response.content)

        self.assertEqual(
            r['project'],
            {
                'id': allocation.project.pk,
                'title': allocation.project.title,
                'description': allocation.project.description,
                'pi': allocation.project.pi.username,
                'field_of_science': allocation.project.field_of_science.description,
                'status': allocation.project.status.name
            }
        )
        self.assertEqual(r['description'], allocation.description)
        self.assertEqual(
            r['resource'],
            {'name': 'Devstack', 'resource_type': 'OpenStack'}
        )
        self.assertEqual(r['status'], 'Active')
        self.assertEqual(
            r['attributes'],
            {
                attributes.ALLOCATION_PROJECT_ID: allocated_project_id,
                attributes.ALLOCATION_PROJECT_NAME: allocated_project_name
            }
        )
        self.assertEqual(len(r['attributes'].keys()), 2)
