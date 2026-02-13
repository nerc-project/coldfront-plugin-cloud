import os
import time
import unittest
import uuid

from coldfront_plugin_cloud import attributes, openshift, tasks, utils
from coldfront_plugin_cloud.tests import base

from django.core.management import call_command
import kubernetes.dynamic.exceptions as kexc


@unittest.skipUnless(os.getenv("FUNCTIONAL_TESTS"), "Functional tests not enabled.")
class TestAllocation(base.TestBase):
    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_openshift_resource(
            name="Microshift",
            api_url=os.getenv("OS_API_URL"),
        )
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_REQUESTS_NESE_STORAGE,
            resource_name=self.resource.name,
            quota_label="ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage",
            multiplier=20,
            static_quota=0,
            unit_suffix="Gi",
        )
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_REQUESTS_GPU,
            resource_name=self.resource.name,
            quota_label="requests.nvidia.com/gpu",
            multiplier=0,
        )

    def test_new_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        # Check project
        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        self.assertIsNotNone(project_id)
        self.assertIsNotNone(
            allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME)
        )

        allocator._get_project(project_id)

        # Check default limit ranges
        limit_ranges = allocator._openshift_get_limits(project_id)
        self.assertEqual(len(limit_ranges["items"]), 1)
        self.assertEqual(
            limit_ranges["items"][0]["metadata"]["name"], f"{project_id}-limits"
        )

        # Check user and roles
        user_info = allocator.get_federated_user(user.username)
        self.assertEqual(user_info, {"username": user.username})

        allocator._get_role(user.username, project_id)

        allocator.remove_role_from_user(user.username, project_id)

        with self.assertRaises(openshift.NotFound):
            allocator._get_role(user.username, project_id)

        allocator.disable_project(project_id)

        # Deleting a project is not instantaneous on OpenShift
        time.sleep(10)
        with self.assertRaises(kexc.NotFoundError):
            allocator._get_project(project_id)

    def test_add_remove_user(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        self.new_project_user(user, project)
        allocation = self.new_allocation(project, self.resource, 1)
        self.new_allocation_user(allocation, user)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        user2 = self.new_user()
        self.new_project_user(user2, project)
        allocation_user2 = self.new_allocation_user(allocation, user2)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        tasks.add_user_to_allocation(allocation_user2.pk)
        allocator._get_role(user.username, project_id)

        user_info = allocator.get_federated_user(user.username)
        self.assertEqual(user_info, {"username": user.username})

        allocator._get_role(user.username, project_id)
        allocator._get_role(user2.username, project_id)

        assert set([user.username, user2.username]) == allocator.get_users(project_id)

        tasks.remove_user_from_allocation(allocation_user2.pk)

        allocator._get_role(user.username, project_id)
        with self.assertRaises(openshift.NotFound):
            allocator._get_role(user2.username, project_id)

        assert set([user.username]) == allocator.get_users(project_id)

        # use the validate_allocations command to add a new user
        user3 = self.new_user()
        self.new_allocation_user(allocation, user3)
        assert user3.username not in allocator.get_users(project_id)
        call_command("validate_allocations", apply=True)
        assert user3.username in allocator.get_users(project_id)

        # directly add a user to openshift which should then be
        # deleted when validate_allocations is called
        non_coldfront_user = uuid.uuid4().hex
        allocator.get_or_create_federated_user(non_coldfront_user)
        allocator.assign_role_on_user(non_coldfront_user, project_id)
        assert non_coldfront_user in allocator.get_users(project_id)
        call_command("validate_allocations", apply=True)
        assert non_coldfront_user not in allocator.get_users(project_id)

    def test_new_allocation_quota(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        self.assertEqual(allocation.get_attribute(attributes.QUOTA_LIMITS_CPU), 2 * 1)
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_LIMITS_MEMORY), 2 * 4096
        )
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB),
            2 * 5,
        )
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_REQUESTS_NESE_STORAGE), 2 * 20
        )
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_REQUESTS_GPU), 2 * 0)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_PVC), 2 * 2)

        quota = allocator.get_quota(project_id)
        # The return value will update to the most relevant unit, so
        # 2000m cores becomes 2 and 8192Mi becomes 8Gi
        self.assertEqual(
            quota,
            {
                "limits.cpu": "2",
                "limits.memory": "8Gi",
                "limits.ephemeral-storage": "10Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "40Gi",
                "requests.nvidia.com/gpu": "0",
                "persistentvolumeclaims": "4",
            },
        )

        # change a bunch of attributes
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_LIMITS_CPU, 6)
        utils.set_attribute_on_allocation(
            allocation, attributes.QUOTA_LIMITS_MEMORY, 8192
        )
        utils.set_attribute_on_allocation(
            allocation, attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB, 50
        )
        utils.set_attribute_on_allocation(
            allocation, attributes.QUOTA_REQUESTS_NESE_STORAGE, 100
        )
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_REQUESTS_GPU, 1)
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_PVC, 10)

        self.assertEqual(allocation.get_attribute(attributes.QUOTA_LIMITS_CPU), 6)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_LIMITS_MEMORY), 8192)
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB), 50
        )
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_REQUESTS_NESE_STORAGE), 100
        )
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_REQUESTS_GPU), 1)
        self.assertEqual(allocation.get_attribute(attributes.QUOTA_PVC), 10)

        # This call should update the openshift quota to match the current attributes
        call_command("validate_allocations", apply=True)

        quota = allocator.get_quota(project_id)
        quota = {k: v for k, v in quota.items() if v is not None}

        self.assertEqual(
            quota,
            {
                "limits.cpu": "6",
                "limits.memory": "8Gi",
                "limits.ephemeral-storage": "50Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "100Gi",
                "requests.nvidia.com/gpu": "1",
                "persistentvolumeclaims": "10",
            },
        )

    def test_reactivate_allocation(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        self.assertEqual(allocation.get_attribute(attributes.QUOTA_LIMITS_CPU), 2)

        quota = allocator.get_quota(project_id)

        # The return value will update to the most relevant unit, so
        # 2000m cores becomes 2 and 8192Mi becomes 8Gi
        self.assertEqual(
            quota,
            {
                "limits.cpu": "2",
                "limits.memory": "8Gi",
                "limits.ephemeral-storage": "10Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "40Gi",
                "requests.nvidia.com/gpu": "0",
                "persistentvolumeclaims": "4",
            },
        )

        # Simulate an attribute change request and subsequent approval which
        # triggers a reactivation
        utils.set_attribute_on_allocation(allocation, attributes.QUOTA_LIMITS_CPU, 3)
        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        quota = allocator.get_quota(project_id)
        # The return value will update to the most relevant unit, so
        # 3000m cores becomes 3 and 8192Mi becomes 8Gi
        self.assertEqual(
            quota,
            {
                "limits.cpu": "3",
                "limits.memory": "8Gi",
                "limits.ephemeral-storage": "10Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "40Gi",
                "requests.nvidia.com/gpu": "0",
                "persistentvolumeclaims": "4",
            },
        )

        allocator._get_role(user.username, project_id)

    def test_project_default_labels(self):
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        # Check project labels
        namespace_dict_labels = allocator._openshift_get_namespace(project_id)[
            "metadata"
        ]["labels"]
        self.assertTrue(
            namespace_dict_labels.items() > openshift.PROJECT_DEFAULT_LABELS.items()
        )

        # What if we have a new custom label, or changed value?
        openshift.PROJECT_DEFAULT_LABELS["test"] = "test"
        call_command("validate_allocations", apply=True)

        namespace_dict_labels = allocator._openshift_get_namespace(project_id)[
            "metadata"
        ]["labels"]
        self.assertTrue(
            namespace_dict_labels.items() > openshift.PROJECT_DEFAULT_LABELS.items()
        )

        # What if a deafult label is removed (or cloud label
        # already has other unrelated labels)? Cloud label should still remain
        del openshift.PROJECT_DEFAULT_LABELS["test"]
        call_command("validate_allocations", apply=True)
        namespace_dict_labels = allocator._openshift_get_namespace(project_id)[
            "metadata"
        ]["labels"]
        self.assertFalse(
            openshift.PROJECT_DEFAULT_LABELS.items() > {"test": "test"}.items()
        )
        self.assertTrue(namespace_dict_labels.items() > {"test": "test"}.items())
        self.assertTrue(
            namespace_dict_labels.items() > openshift.PROJECT_DEFAULT_LABELS.items()
        )

    def test_create_incomplete(self):
        """Creating a user that only has user, but no identity or mapping should not raise an error."""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)
        user_def = {
            "metadata": {"name": user.username},
            "fullName": user.username,
        }

        allocator._openshift_create_user(user_def)
        self.assertTrue(allocator._openshift_user_exists(user.username))
        self.assertFalse(allocator._openshift_identity_exists(user.username))
        self.assertFalse(
            allocator._openshift_useridentitymapping_exists(
                user.username, user.username
            )
        )

        # Now create identity and mapping, no errors should be raised
        allocator.get_or_create_federated_user(user.username)
        self.assertTrue(allocator._openshift_user_exists(user.username))
        self.assertTrue(allocator._openshift_identity_exists(user.username))
        self.assertTrue(
            allocator._openshift_useridentitymapping_exists(
                user.username, user.username
            )
        )

    def test_migrate_quota_field_names(self):
        """When a quota changes to a new label name, validate_allocations should update the quota."""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        quota = allocator.get_quota(project_id)
        self.assertEqual(
            quota,
            {
                "limits.cpu": "1",
                "limits.memory": "4Gi",
                "limits.ephemeral-storage": "5Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "20Gi",
                "requests.nvidia.com/gpu": "0",
                "persistentvolumeclaims": "2",
            },
        )

        # Now migrate NESE Storage quota field (ocs-external...) to fake storage quota
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_REQUESTS_NESE_STORAGE,
            resource_name=self.resource.name,
            quota_label="fake-storage.storageclass.storage.k8s.io/requests.storage",
            multiplier=20,
            static_quota=0,
            unit_suffix="Gi",
        )
        call_command("validate_allocations", apply=True)

        # Check the quota after migration
        quota = allocator.get_quota(project_id)
        self.assertEqual(
            quota,
            {
                "limits.cpu": "1",
                "limits.memory": "4Gi",
                "limits.ephemeral-storage": "5Gi",
                "fake-storage.storageclass.storage.k8s.io/requests.storage": "20Gi",  # Migrated key
                "requests.nvidia.com/gpu": "0",
                "persistentvolumeclaims": "2",
            },
        )

    def test_needs_renewal_allocation(self):
        """Simple test to validate allocations in `Active (Needs Renewal)` status."""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(
            project, self.resource, 1, "Active (Needs Renewal)"
        )
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        user2 = self.new_user()
        self.new_allocation_user(allocation, user2)

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)
        assert user2.username not in allocator.get_users(project_id)
        call_command("validate_allocations", apply=True)
        assert user2.username in allocator.get_users(project_id)

    def test_limitrange_defaults_update(self):
        """Test validation if default LimitRange changes, or actual LimitRange is deleted."""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        # Check initial limit ranges
        limit_ranges = allocator._openshift_get_limits(project_id)
        self.assertEqual(len(limit_ranges["items"]), 1)
        self.assertEqual(
            openshift.limit_ranges_diff(
                limit_ranges["items"][0]["spec"]["limits"],
                openshift.LIMITRANGE_DEFAULTS,
            ),
            [],
        )

        # Change LimitRange defaults
        new_defaults = [
            {
                "type": "Container",
                "default": {"cpu": "2", "memory": "8192Mi", "nvidia.com/gpu": "1"},
                "defaultRequest": {
                    "cpu": "1",
                    "memory": "4096Mi",
                    "nvidia.com/gpu": "1",
                },
                "min": {"cpu": "100m", "memory": "64Mi"},
            }
        ]
        openshift.LIMITRANGE_DEFAULTS = new_defaults

        call_command("validate_allocations", apply=True)

        limit_ranges = allocator._openshift_get_limits(project_id)
        self.assertEqual(len(limit_ranges["items"]), 1)
        self.assertEqual(
            openshift.limit_ranges_diff(
                limit_ranges["items"][0]["spec"]["limits"], new_defaults
            ),
            [],
        )

        # Delete and re-create limit range using validate_allocations
        allocator._openshift_delete_limits(project_id)
        limit_ranges = allocator._openshift_get_limits(project_id)
        self.assertEqual(len(limit_ranges["items"]), 0)
        call_command("validate_allocations", apply=True)
        limit_ranges = allocator._openshift_get_limits(project_id)
        self.assertEqual(len(limit_ranges["items"]), 1)
        self.assertEqual(
            openshift.limit_ranges_diff(
                limit_ranges["items"][0]["spec"]["limits"], new_defaults
            ),
            [],
        )

    def test_preexisting_project(self):
        """Test allocation activation and validation when the project already exists on OpenShift."""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 1)
        self.new_allocation_user(allocation, user)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        project_id = allocator.create_project(project.title).id

        self.assertEqual(allocator.get_quota(project_id), {})
        self.assertEqual(allocator.get_users(project_id), set())

        utils.set_attribute_on_allocation(
            allocation, attributes.ALLOCATION_PROJECT_ID, project_id
        )
        utils.set_attribute_on_allocation(
            allocation, attributes.ALLOCATION_PROJECT_NAME, project_id
        )
        tasks.activate_allocation(allocation.pk)
        call_command("validate_allocations", apply=True)

        self.assertEqual(
            allocator.get_quota(project_id),
            {
                "limits.cpu": "1",
                "limits.memory": "4Gi",
                "limits.ephemeral-storage": "5Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "20Gi",
                "requests.nvidia.com/gpu": "0",
                "persistentvolumeclaims": "2",
            },
        )
        assert set([user.username]) == allocator.get_users(project_id)

    def test_remove_quota(self):
        """Test removing a quota from a resource and validating allocations.
        After removal, prior allocations should still have the quota, but new allocations should not."""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation_1 = self.new_allocation(project, self.resource, 1)
        allocator_1 = openshift.OpenShiftResourceAllocator(self.resource, allocation_1)

        tasks.activate_allocation(allocation_1.pk)
        allocation_1.refresh_from_db()
        project_id_1 = allocation_1.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        quota = allocator_1.get_quota(project_id_1)
        self.assertIn(
            "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage",
            quota,
        )

        # Now remove NESE Storage quota from resource
        call_command(
            "remove_quota_from_resource",
            resource_name=self.resource.name,
            display_name=attributes.QUOTA_REQUESTS_NESE_STORAGE,
            apply=True,
        )
        call_command(
            "validate_allocations", apply=True
        )  # This should have not removed the quota from prior allocation (Have no impact)

        quota = allocator_1.get_quota(project_id_1)
        self.assertIn(
            "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage",
            quota,
        )
        self.assertIsNotNone(
            allocation_1.get_attribute(attributes.QUOTA_REQUESTS_NESE_STORAGE)
        )

        # Create second allocation, which should not have the NESE storage quota
        self.resource.refresh_from_db()
        project_2 = self.new_project(pi=user)
        allocation_2 = self.new_allocation(project_2, self.resource, 1)
        allocator_2 = openshift.OpenShiftResourceAllocator(self.resource, allocation_2)
        tasks.activate_allocation(allocation_2.pk)
        allocation_2.refresh_from_db()
        project_id_2 = allocation_2.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        quota_2 = allocator_2.get_quota(project_id_2)
        self.assertNotIn(
            "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage",
            quota_2,
        )
        self.assertIsNone(
            allocation_2.get_attribute(attributes.QUOTA_REQUESTS_NESE_STORAGE)
        )


class TestAllocationNewQuota(base.TestBase):
    def setUp(self) -> None:
        super().setUp()
        self.resource = self.new_openshift_resource(
            name="Microshift",
            api_url=os.getenv("OS_API_URL"),
        )

    def test_allocation_new_attribute(self):
        """When a new attribute is introduced, but pre-existing allocations don't have it"""
        user = self.new_user()
        project = self.new_project(pi=user)
        allocation = self.new_allocation(project, self.resource, 2)
        allocator = openshift.OpenShiftResourceAllocator(self.resource, allocation)

        tasks.activate_allocation(allocation.pk)
        allocation.refresh_from_db()

        project_id = allocation.get_attribute(attributes.ALLOCATION_PROJECT_ID)

        self.assertEqual(allocation.get_attribute(attributes.QUOTA_LIMITS_CPU), 2 * 1)

        quota = allocator.get_quota(project_id)
        self.assertEqual(
            quota,
            {
                "limits.cpu": "2",
                "limits.memory": "8Gi",
                "limits.ephemeral-storage": "10Gi",
                "persistentvolumeclaims": "4",
            },  # Note no ceph storage quota
        )

        # Add a new attribute for Openshift
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_REQUESTS_NESE_STORAGE,
            resource_name=self.resource.name,
            quota_label="ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage",
            multiplier=20,
            static_quota=0,
            unit_suffix="Gi",
        )

        call_command("validate_allocations", apply=True)
        allocation.refresh_from_db()

        self.assertEqual(allocation.get_attribute(attributes.QUOTA_LIMITS_CPU), 2 * 1)
        self.assertEqual(
            allocation.get_attribute(attributes.QUOTA_LIMITS_MEMORY), 2 * 4096
        )

        quota = allocator.get_quota(project_id)
        self.assertEqual(
            quota,
            {
                "limits.cpu": "2",
                "limits.memory": "8Gi",
                "limits.ephemeral-storage": "10Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "40Gi",
                "persistentvolumeclaims": "4",
            },
        )
