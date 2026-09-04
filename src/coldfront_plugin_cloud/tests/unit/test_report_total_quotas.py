import json
from io import StringIO

from django.core.management import call_command

from coldfront_plugin_cloud import attributes, utils
from coldfront_plugin_cloud.tests import base


class TestReportTotalQuotas(base.TestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.resource = cls.new_openstack_resource(name="test-quota-totals")
        call_command("register_default_quotas", apply=True)

    def report(self, **kwargs):
        out = StringIO()
        call_command("report_total_quotas", stdout=out, **kwargs)
        return json.loads(out.getvalue())

    def test_totals_across_allocations(self):
        for vcpus in (2, 5):
            project = self.new_project()
            allocation = self.new_allocation(project, self.resource, 1)
            utils.set_attribute_on_allocation(allocation, attributes.QUOTA_VCPU, vcpus)

        (row,) = [r for r in self.report(cloud_type="OpenStack")]
        self.assertEqual(row["allocations"], 2)
        self.assertEqual(row["quotas"][attributes.QUOTA_VCPU], 7.0)
        # Quotas with no value set still report as zero.
        self.assertEqual(row["quotas"][attributes.QUOTA_FLOATING_IPS], 0.0)

    def test_per_project_and_project_id_filter(self):
        project_a = self.new_project()
        project_b = self.new_project()
        for project, vcpus in ((project_a, 3), (project_b, 4)):
            allocation = self.new_allocation(project, self.resource, 1)
            utils.set_attribute_on_allocation(allocation, attributes.QUOTA_VCPU, vcpus)

        rows = self.report(cloud_type="OpenStack", per_project=True)
        totals = {r["project_id"]: r["quotas"][attributes.QUOTA_VCPU] for r in rows}
        self.assertEqual(totals[project_a.id], 3.0)
        self.assertEqual(totals[project_b.id], 4.0)

        (scoped,) = self.report(cloud_type="OpenStack", project_id=project_a.id)
        self.assertEqual(scoped["quotas"][attributes.QUOTA_VCPU], 3.0)
        self.assertEqual(scoped["allocations"], 1)
