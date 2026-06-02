from django.contrib.auth.models import User
from coldfront.core.resource.models import ResourceAttribute, ResourceAttributeType

from coldfront_plugin_cloud import tasks, kc_client, attributes, utils
from coldfront_plugin_cloud.tests import base


class TestKeyCloakUserManagement(base.TestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.kc_admin_client = kc_client.KeyCloakAPIClient()
        cls.resource = cls.new_openshift_resource(
            name="Test Resource",
        )
        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_KEYCLOAK_GROUP_TEMPLATE
            ),
            resource=cls.resource,
            value="$resource_name/$allocated_project_id",
        )

    def new_keycloak_user(self, cf_username):
        url = f"{self.kc_admin_client.base_url}/admin/realms/{self.kc_admin_client.realm}/users"
        payload = {
            "username": cf_username,
            "enabled": True,
            "email": cf_username,
        }
        r = self.kc_admin_client.api_client.post(url, json=payload)
        r.raise_for_status()

    def new_user(self, username=None, add_to_keycloak=True) -> User:
        user = super().new_user(username)
        if add_to_keycloak:
            self.new_keycloak_user(user.username)
        return user

    def new_allocation(
        self, project, resource, quantity, status="Active", attr_value="Test Value"
    ):
        allocation = super().new_allocation(project, resource, quantity, status)
        utils.set_attribute_on_allocation(
            allocation, attributes.ALLOCATION_PROJECT_ID, attr_value
        )
        return allocation

    def test_user_added_to_allocation(self):
        """Test that when a user is added to an allocation, they exist in Keycloak and are in the project group."""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocation_user = self.new_allocation_user(allocation, user)

        # Simulate triggering the allocation activate signal
        tasks.add_user_to_keycloak(allocation_user.pk)

        # Check that the user exists in Keycloak
        user_id = self.kc_admin_client.get_user_id(user.username)
        self.assertIsNotNone(user_id)

        # Check that the user is in the project group
        # Group name determined by the RESOURCE_KEYCLOAK_GROUP_TEMPLATE attribute, set to "$resource_name/$allocated_project_id" in tests
        user_groups = self.kc_admin_client.get_user_groups(user_id)
        self.assertIn(f"{self.resource.name}/Test Value", user_groups)

    def test_user_removed_from_allocation(self):
        """Test that when a user is removed from an allocation, they are removed from the project group."""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocation_user = self.new_allocation_user(allocation, user)

        tasks.add_user_to_keycloak(allocation_user.pk)

        user_id = self.kc_admin_client.get_user_id(user.username)
        user_groups = self.kc_admin_client.get_user_groups(user_id)
        self.assertIn(f"{self.resource.name}/Test Value", user_groups)

        tasks.remove_user_from_keycloak(allocation_user.pk)

        # Check that the user is no longer in the group
        user_groups = self.kc_admin_client.get_user_groups(user_id)
        self.assertNotIn(f"{self.resource.name}/Test Value", user_groups)

    def test_user_not_in_keycloak_added_to_allocation(self):
        """Test that when a user not in Keycloak is added to an allocation, they are not added to the group."""
        user = self.new_user(add_to_keycloak=False)
        project = self.new_project(pi=user)
        allocation = self.new_allocation(
            project, self.resource, 1, attr_value="Test Not Created"
        )
        allocation_user = self.new_allocation_user(allocation, user)

        # Should not raise error
        tasks.add_user_to_keycloak(allocation_user.pk)

        user_id = self.kc_admin_client.get_user_id(user.username)
        self.assertIsNone(user_id)

        # Verify the group was not created at all
        group_id = self.kc_admin_client.get_group_id(
            f"{self.resource.name}/Test Not Created"
        )
        self.assertIsNone(group_id)

    def test_user_not_in_keycloak_removed_from_allocation(self):
        """Test that when a user not in Keycloak is removed from an allocation, no error occurs."""
        user = self.new_user(add_to_keycloak=False)
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocation_user = self.new_allocation_user(allocation, user)

        # Verify the user doesn't exist in Keycloak
        user_id = self.kc_admin_client.get_user_id(user.username)
        self.assertIsNone(user_id)

        # Try to remove the user from the allocation (should not raise an error)
        tasks.remove_user_from_keycloak(allocation_user.pk)

    def test_multiple_users_in_same_allocation(self):
        """Test that multiple users can be added to the same allocation and are all in the group."""
        pi = self.new_user()
        project = self.new_project(pi=pi)
        allocation = self.new_allocation(project, self.resource, 2)

        # Add multiple users to the allocation
        users = [self.new_user() for _ in range(3)]
        allocation_users = [
            self.new_allocation_user(allocation, user) for user in users
        ]

        for allocation_user in allocation_users:
            tasks.add_user_to_keycloak(allocation_user.pk)

        # Verify all users are in the group
        for user in users:
            user_id = self.kc_admin_client.get_user_id(user.username)
            user_groups = self.kc_admin_client.get_user_groups(user_id)
            self.assertIn(f"{self.resource.name}/Test Value", user_groups)

    def test_remove_one_user_keeps_others_in_group(self):
        """Test that removing one user from an allocation doesn't affect other users in the group."""
        pi = self.new_user()
        project = self.new_project(pi=pi)
        allocation = self.new_allocation(project, self.resource, 2)

        users = [self.new_user() for _ in range(2)]
        allocation_users = [
            self.new_allocation_user(allocation, user) for user in users
        ]

        for allocation_user in allocation_users:
            tasks.add_user_to_keycloak(allocation_user.pk)

        tasks.remove_user_from_keycloak(allocation_users[0].pk)

        # Verify all users except the removed one are still in the group
        user1_id = self.kc_admin_client.get_user_id(users[0].username)
        user1_groups = self.kc_admin_client.get_user_groups(user1_id)
        self.assertNotIn(f"{self.resource.name}/Test Value", user1_groups)

        user2_id = self.kc_admin_client.get_user_id(users[1].username)
        user2_groups = self.kc_admin_client.get_user_groups(user2_id)
        self.assertIn(f"{self.resource.name}/Test Value", user2_groups)

    def test_user_in_multiple_allocations_groups(self):
        """Test that a user can be in multiple project groups from different allocations."""
        user = self.new_user()

        project1 = self.new_project(pi=user)
        allocation1 = self.new_allocation(
            project1, self.resource, 1, attr_value="Test Value 1"
        )

        project2 = self.new_project(pi=user)
        allocation2 = self.new_allocation(
            project2, self.resource, 1, attr_value="Test Value 2"
        )

        # Add user to both allocations
        allocation_user1 = self.new_allocation_user(allocation1, user)
        allocation_user2 = self.new_allocation_user(allocation2, user)

        tasks.add_user_to_keycloak(allocation_user1.pk)
        tasks.add_user_to_keycloak(allocation_user2.pk)

        # Verify user is in both groups
        user_id = self.kc_admin_client.get_user_id(user.username)
        user_groups = self.kc_admin_client.get_user_groups(user_id)
        self.assertIn(f"{self.resource.name}/Test Value 1", user_groups)
        self.assertIn(f"{self.resource.name}/Test Value 2", user_groups)

        # Remove user from first allocation
        tasks.remove_user_from_keycloak(allocation_user1.pk)

        # Verify user is now only in second group
        user_groups = self.kc_admin_client.get_user_groups(user_id)
        self.assertNotIn(f"{self.resource.name}/Test Value 1", user_groups)
        self.assertIn(f"{self.resource.name}/Test Value 2", user_groups)

    def test_user_added_without_keycloak_group_template(self):
        """Test that when the Keycloak group template attribute is not present on the resource, the user is not added to group and a log message is captured."""
        # Create a resource without the Keycloak group template attribute
        resource_no_template = self.new_openshift_resource(name="Resource No Template")

        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(
            project, resource_no_template, 1, attr_value="Test No Template"
        )
        allocation_user = self.new_allocation_user(allocation, user)

        # Capture the log message
        with self.assertLogs("coldfront_plugin_cloud.tasks", level="INFO") as log:
            tasks.add_user_to_keycloak(allocation_user.pk)

        # Verify the warning was logged
        self.assertEqual(len(log.records), 1)
        self.assertIn(
            "Keycloak enabled but no group name template specified for resource Resource No Template",
            log.records[0].getMessage(),
        )
        self.assertIn(resource_no_template.name, log.records[0].getMessage())

        # Verify the user exists in Keycloak but is not in any groups
        user_id = self.kc_admin_client.get_user_id(user.username)
        self.assertIsNotNone(user_id)
        user_groups = self.kc_admin_client.get_user_groups(user_id)
        self.assertEqual(user_groups, [])
