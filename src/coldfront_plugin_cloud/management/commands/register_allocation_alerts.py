from datetime import datetime, timezone, timedelta

from django.core.management.base import BaseCommand
from django_q.tasks import schedule, Schedule


import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Registers a django-q schedule that updates allocations based on set criterias. The schedule runs everyday
    """

    def handle(self, *args, **options):
        date = datetime.now(timezone.utc) + timedelta(days=1)
        date = date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )  # TODO: What time of day to run this job?
        schedule(
            "coldfront_plugin_cloud.tasks.remind_allocations_revoked",
            schedule_type=Schedule.DAILY,
            next_run=date,
        )
