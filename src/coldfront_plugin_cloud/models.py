from django.db import models
from model_utils.models import TimeStampedModel
from coldfront.core.allocation.models import Allocation


class AllocationDailyBillableUsage(TimeStampedModel):
    """Stores daily billable usage for allocations by SU type."""

    allocation = models.ForeignKey(
        Allocation,
        on_delete=models.CASCADE,
        related_name="daily_usage_records",
        help_text="The allocation this usage belongs to",
    )
    date = models.DateField(help_text="The date for which this usage was recorded")
    su_type = models.CharField(
        max_length=255,
        help_text="The type of Service Unit (e.g., OpenStack CPU, OpenStack V100 GPU)",
    )
    value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="The usage value/cost for this SU type on this date",
    )

    class Meta:
        db_table = "coldfront_plugin_cloud_allocationdailybillableusage"
        unique_together = [["allocation", "date", "su_type"]]
        indexes = [
            models.Index(fields=["allocation", "date"]),
            models.Index(fields=["date"]),
        ]
        ordering = ["-date", "allocation", "su_type"]

    def __str__(self):
        return f"{self.allocation.id} - {self.date} - {self.su_type}: {self.value}"
