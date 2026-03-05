import json

from django.core.management import call_command

from coldfront_plugin_cloud.tests.base import TestBase
from coldfront_plugin_cloud import attributes


class TestRegisterDefaultQuotas(TestBase):
    """Unit tests for the ``register_default_quotas`` management command.

    This command is intended to be idempotent.  The first invocation should
    populate the ``Available Quota Resources`` attribute on OpenShift and
    OpenStack resources, and a second invocation should make no changes.
    """

    def test_register_default_quotas_idempotent(self):
        # create one of each resource type
        openshift_resource = self.new_openshift_resource(name="test-oshift")
        openstack_resource = self.new_openstack_resource(name="test-osstack")

        call_command("register_default_quotas", apply=True)

        def load_quotas(resource):
            val = resource.get_attribute(attributes.RESOURCE_QUOTA_RESOURCES)
            self.assertIsNotNone(val, "quota attribute should be defined")
            return json.loads(val)

        openshift_quota_dict = load_quotas(openshift_resource)
        openstack_quota_dict = load_quotas(openstack_resource)

        # verify that each expected display name is present
        expected_openshift_keys = {
            attributes.QUOTA_LIMITS_CPU,
            attributes.QUOTA_LIMITS_MEMORY,
            attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB,
            attributes.QUOTA_PVC,
            attributes.QUOTA_REQUESTS_NESE_STORAGE,
            attributes.QUOTA_REQUESTS_GPU,
        }
        self.assertEqual(
            set(openshift_quota_dict.keys()),
            expected_openshift_keys,
            "OpenShift resource should have exactly the default quotas",
        )

        expected_openstack_keys = {
            attributes.QUOTA_INSTANCES,
            attributes.QUOTA_VCPU,
            attributes.QUOTA_RAM,
            attributes.QUOTA_VOLUMES,
            attributes.QUOTA_VOLUMES_GB,
            attributes.QUOTA_FLOATING_IPS,
            attributes.QUOTA_OBJECT_GB,
        }
        self.assertEqual(
            set(openstack_quota_dict.keys()),
            expected_openstack_keys,
            "OpenStack resource should have exactly the default quotas",
        )

        # spot-check a few of the fields to ensure values are correct
        osh_cpu = openshift_quota_dict[attributes.QUOTA_LIMITS_CPU]
        self.assertEqual(osh_cpu["quota_label"], "limits.cpu")
        self.assertEqual(osh_cpu["multiplier"], 1)

        osst_ram = openstack_quota_dict[attributes.QUOTA_RAM]
        self.assertEqual(osst_ram["quota_label"], "compute.ram")
        self.assertEqual(osst_ram["multiplier"], 4096)

        # run the command again; since quotas already exist nothing should
        call_command("register_default_quotas", apply=True)

        openshift_after = load_quotas(openshift_resource)
        openstack_after = load_quotas(openstack_resource)

        self.assertEqual(
            openshift_quota_dict,
            openshift_after,
            "Repeated invocation should not mutate OpenShift quotas",
        )
        self.assertEqual(
            openstack_quota_dict,
            openstack_after,
            "Repeated invocation should not mutate OpenStack quotas",
        )

    def test_register_default_quotas_with_existing_quota(self):
        resource = self.new_openshift_resource(name="existing-quota")
        call_command(
            "add_quota_to_resource",
            display_name=attributes.QUOTA_LIMITS_CPU,
            resource_name=resource.name,
            quota_label="limits.cpu",
            multiplier=1,
        )

        # running the migration should detect that the attribute exists and skip
        call_command("register_default_quotas", apply=True)

        # only the manually added quota should remain
        val = resource.get_attribute(attributes.RESOURCE_QUOTA_RESOURCES)
        quotas = json.loads(val)
        self.assertEqual(
            set(quotas.keys()),
            {attributes.QUOTA_LIMITS_CPU},
            "Resource should only have the pre-existing CPU quota",
        )
        self.assertEqual(
            quotas[attributes.QUOTA_LIMITS_CPU]["quota_label"], "limits.cpu"
        )
        self.assertEqual(quotas[attributes.QUOTA_LIMITS_CPU]["multiplier"], 1)
