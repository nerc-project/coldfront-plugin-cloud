# Generated manually for coldfront_plugin_cloud

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("allocation", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="AllocationDailyBillableUsage",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "date",
                    models.DateField(
                        help_text="The date for which this usage was recorded"
                    ),
                ),
                (
                    "su_type",
                    models.CharField(
                        help_text="The type of Service Unit (e.g., OpenStack CPU, OpenStack V100 GPU)",
                        max_length=255,
                    ),
                ),
                (
                    "value",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="The usage value/cost for this SU type on this date",
                        max_digits=12,
                    ),
                ),
                (
                    "allocation",
                    models.ForeignKey(
                        help_text="The allocation this usage belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_usage_records",
                        to="allocation.allocation",
                    ),
                ),
            ],
            options={
                "db_table": "coldfront_plugin_cloud_allocationdailybillableusage",
                "ordering": ["-date", "allocation", "su_type"],
            },
        ),
        migrations.AddIndex(
            model_name="allocationdailybillableusage",
            index=models.Index(
                fields=["allocation", "date"], name="coldfront_p_allocat_5c8e3d_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="allocationdailybillableusage",
            index=models.Index(fields=["date"], name="coldfront_p_date_3e8a9e_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="allocationdailybillableusage",
            unique_together={("allocation", "date", "su_type")},
        ),
    ]
