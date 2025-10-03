import os
import time
import unittest
from unittest import mock
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
            ibm_storage_available=True,
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
                "ibm-spectrum-scale-fileset.storageclass.storage.k8s.io/requests.storage": "0",
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
                "ibm-spectrum-scale-fileset.storageclass.storage.k8s.io/requests.storage": "0",
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
                "ibm-spectrum-scale-fileset.storageclass.storage.k8s.io/requests.storage": "0",
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
                "ibm-spectrum-scale-fileset.storageclass.storage.k8s.io/requests.storage": "0",
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

    @mock.patch.object(
        tasks,
        "UNIT_QUOTA_MULTIPLIERS",
        {
            "openshift": {
                attributes.QUOTA_LIMITS_CPU: 1,
            }
        },
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
            },
        )

        # Add a new attribute for Openshift
        tasks.UNIT_QUOTA_MULTIPLIERS["openshift"][attributes.QUOTA_LIMITS_MEMORY] = 4096

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
            },
        )

    def test_migrate_quota_field_names(self):
        """When a quota key in QUOTA_KEY_MAPPING changes to a new value, validate_allocations should update the quota."""
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
                "ibm-spectrum-scale-fileset.storageclass.storage.k8s.io/requests.storage": "0",
                "requests.nvidia.com/gpu": "0",
                "persistentvolumeclaims": "2",
            },
        )

        # Now migrate NESE Storage quota field (ocs-external...) to fake storage quota
        with unittest.mock.patch.dict(
            openshift.OpenShiftResourceAllocator.QUOTA_KEY_MAPPING,
            {
                attributes.QUOTA_REQUESTS_NESE_STORAGE: lambda x: {
                    "fake-storage.storageclass.storage.k8s.io/requests.storage": f"{x}Gi"
                }
            },
        ):
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
                "ibm-spectrum-scale-fileset.storageclass.storage.k8s.io/requests.storage": "0",
                "requests.nvidia.com/gpu": "0",
                "persistentvolumeclaims": "2",
            },
        )

    def test_ibm_storage_not_available(self):
        """If IBM Scale storage is not available, the corresponding quotas should not be set."""
        user = self.new_user()
        project = self.new_project(pi=user)

        # Set ibm storage as not available
        self.resource.resourceattribute_set.filter(
            resource_attribute_type__name=attributes.RESOURCE_IBM_AVAILABLE
        ).update(value="false")
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

        # Now set IBM Scale storage as available
        self.resource.resourceattribute_set.filter(
            resource_attribute_type__name=attributes.RESOURCE_IBM_AVAILABLE
        ).update(value="true")

        call_command("validate_allocations", apply=True)

        quota = allocator.get_quota(project_id)
        self.assertEqual(
            quota,
            {
                "limits.cpu": "1",
                "limits.memory": "4Gi",
                "limits.ephemeral-storage": "5Gi",
                "ocs-external-storagecluster-ceph-rbd.storageclass.storage.k8s.io/requests.storage": "20Gi",
                "ibm-spectrum-scale-fileset.storageclass.storage.k8s.io/requests.storage": "0",  # Newly added IBM key
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
