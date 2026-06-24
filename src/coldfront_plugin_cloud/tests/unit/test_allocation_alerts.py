from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from coldfront_plugin_cloud.tasks import remind_allocations_revoked
from coldfront_plugin_cloud.tests import base


class TestAllocationAlerts(base.TestBase):
    @patch("coldfront_plugin_cloud.tasks.EMAIL_SENDER", "test@example.com")
    def test_remind_allocations_expired(self):
        """Test that remind_allocations_expired sends emails for allocations expiring soon."""
        # Setup mock datetime to control what "now" returns
        # fake_now = datetime(2025, 11, 1, tzinfo=timezone.utc)
        # mock_datetime.now.return_value = fake_now

        # Create test data
        resource = self.new_openstack_resource(
            name="TestResource", internal_name="TestResource"
        )
        project = self.new_project()

        # Create allocation expiring in 30 days (should trigger reminder)
        allocation = self.new_allocation(
            project=project,
            resource=resource,
            quantity=1,
            status="Expired",
        )

        manager = self.new_user()
        self.new_project_user(manager, project, role="Manager")

        expiration_date = datetime.now(timezone.utc) + timedelta(days=30)
        allocation.end_date = expiration_date
        allocation.save()

        with patch("coldfront.core.utils.mail.send_email") as mock_send_email:
            remind_allocations_revoked()

            # Assert mail.send_email was called once
            mock_send_email.assert_called_once_with(
                subject="Allocation Expiration Reminder",
                sender="test@example.com",
                receiver_list=[allocation.project.pi.email],
                cc=[manager.email],
                body="",
            )
