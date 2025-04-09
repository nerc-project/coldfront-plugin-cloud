import re
import secrets
from random import randrange

from coldfront.core.allocation import models as allocation_models

from coldfront_plugin_cloud.tests import base
from coldfront_plugin_cloud import utils, attributes

MiB_IN_GiB = 1024

class TestGetSanitizedProjectName(base.TestBase):
    def test_project_name(self):
        # Ensure that the sanitized project name conforms to DNS 1123 spec (besides the max length)
        project_name = "---TEST - Software & Application Innovation Lab (SAIL) - TEST Projects   "
        sanitized_name = utils.get_sanitized_project_name(project_name)
        self.assertTrue(re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", sanitized_name))

    def test_get_unique_project_name_length(self):
        project_name = secrets.token_hex(100)
        max_length = randrange(50, 60)

        self.assertGreater(len(project_name), max_length)
        new_name = utils.get_unique_project_name(project_name, max_length=max_length)
        self.assertEqual(len(new_name), max_length)

class TestCheckChangeRequests(base.TestBase):
    def setUp(self):
        super().setUp()
        # Create test allocation change request and attribute change requests
        cpu_quota_attr = allocation_models.AllocationAttributeType.objects.get(
            name=attributes.QUOTA_LIMITS_CPU
        )
        memory_quota_attr = allocation_models.AllocationAttributeType.objects.get(
            name=attributes.QUOTA_LIMITS_MEMORY
        )
        test_attr = allocation_models.AllocationAttributeType.objects.get( 
            name=attributes.ALLOCATION_PROJECT_ID  # Not quota attr, should be ignored
        ) 

        self.allo = self.new_allocation(self.new_project(), self.new_openshift_resource(), 1)
        self.allo_cr = allocation_models.AllocationChangeRequest.objects.create(
            allocation=self.allo,
            status=allocation_models.AllocationChangeStatusChoice.objects.first(),  # Doesn't matter which status
        )
        self.allo_attr_cr_cpu = allocation_models.AllocationAttributeChangeRequest.objects.create(
            allocation_change_request=self.allo_cr,
            allocation_attribute=allocation_models.AllocationAttribute.objects.create(
                allocation=self.allo,
                allocation_attribute_type=cpu_quota_attr,
                value=8,
            ),
            new_value=2,
        )
        self.allo_attr_cr_memory = allocation_models.AllocationAttributeChangeRequest.objects.create(
            allocation_change_request=self.allo_cr,
            allocation_attribute=allocation_models.AllocationAttribute.objects.create(
                allocation=self.allo,
                allocation_attribute_type=memory_quota_attr,
                value=16 * MiB_IN_GiB,
            ),
            new_value=4 * MiB_IN_GiB,
        )
        self.allo_attr_cr_test = allocation_models.AllocationAttributeChangeRequest.objects.create(
            allocation_change_request=self.allo_cr,
            allocation_attribute=allocation_models.AllocationAttribute.objects.create(
                allocation=self.allo,
                allocation_attribute_type=test_attr,
                value=1,
            ),
            new_value=10,
        )

    def test_check_cr_only_decreases(self):
        # True case, test attr should be ignored
        self.assertTrue(utils.check_cr_only_decreases(self.allo_cr.pk))

        # One attribute increases, should return False
        self.allo_attr_cr_cpu.new_value = 100
        self.allo_attr_cr_cpu.save()
        self.assertFalse(utils.check_cr_only_decreases(self.allo_cr.pk))

        # Attribute is not int, current behavior is an error
        self.allo_attr_cr_cpu.new_value = "test"
        self.allo_attr_cr_cpu.save()
        with self.assertRaises(ValueError):
            utils.check_cr_only_decreases(self.allo_cr.pk)

    def test_check_cr_set_to_zero(self):
        # True case, test attr should be ignored
        self.allo_attr_cr_cpu.new_value = 0
        self.allo_attr_cr_cpu.save()
        self.assertTrue(utils.check_cr_set_to_zero(self.allo_cr.pk))

        # One attribute increases, should return False
        self.allo_attr_cr_cpu.new_value = 1
        self.allo_attr_cr_cpu.save()
        self.assertFalse(utils.check_cr_set_to_zero(self.allo_cr.pk))

        # Attribute is not int, current behavior is an error
        self.allo_attr_cr_cpu.new_value = "test"
        self.allo_attr_cr_cpu.save()
        with self.assertRaises(ValueError):
            utils.check_cr_only_decreases(self.allo_cr.pk)

    def test_check_usage_is_lower(self):
        # True case, test attr should be ignored
        test_quota_usage = {
            "limits.cpu": "1",
            "limits.memory": "2Gi",
            "limits.ephemeral-storage": "10Gi",    # Other quotas should be ignored
            "requests.storage": "40Gi",
            "requests.nvidia.com/gpu": "0",
            "persistentvolumeclaims": "4",
        }
        self.assertTrue(utils.check_usage_is_lower(self.allo_cr.pk, test_quota_usage))

        # Requested cpu (2) lower than current used, should return False
        test_quota_usage["limits.cpu"] = "16"
        self.assertFalse(utils.check_usage_is_lower(self.allo_cr.pk, test_quota_usage))
