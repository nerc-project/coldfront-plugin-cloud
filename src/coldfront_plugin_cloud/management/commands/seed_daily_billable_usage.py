import calendar
from datetime import date as date_type

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from coldfront.core.allocation.models import Allocation
from coldfront_plugin_cloud.models import usage_models
from coldfront_plugin_cloud.models.daily_billable_usage import (
    AllocationDailyBillableUsage,
)

DEFAULT_USAGE = {
    "OpenStack CPU": "100.00",
    "OpenStack V100 GPU": "50.00",
    "Storage": "30.12",
}


def dates_in_month(month: str) -> list[str]:
    """Return YYYY-MM-DD strings for every day in month (YYYY-MM)."""
    usage_models.validate_date_str(f"{month}-01")
    year, mon = map(int, month.split("-", 1))
    _, last_day = calendar.monthrange(year, mon)
    return [f"{year}-{mon:02d}-{day:02d}" for day in range(1, last_day + 1)]


_RAMP_STEP = {
    "OpenStack CPU": 5,
    "OpenStack V100 GPU": 2,
    "Storage": 0.5,
}


def usage_for_day(
    base: dict[str, str], day_index: int, ramp: bool
) -> usage_models.UsageInfo:
    if not ramp:
        return usage_models.UsageInfo(base)
    ramped = {}
    for su_type, amount in base.items():
        step = _RAMP_STEP.get(su_type, 0)
        ramped_value = usage_models.Decimal(amount) + usage_models.Decimal(
            day_index
        ) * usage_models.Decimal(str(step))
        ramped[su_type] = str(ramped_value)
    return usage_models.UsageInfo(ramped)


def _current_month_str() -> str:
    today = date_type.today()
    return f"{today.year}-{today.month:02d}"


def seed_daily_billable_usage(
    *,
    allocation_id: int,
    date: str | None = None,
    month: str | None = None,
    current_month: bool = False,
    su: list[str] | None = None,
    ramp: bool = False,
    through_today: bool = False,
) -> dict:
    """Insert test AllocationDailyBillableUsage rows for local development.

    Returns a summary dict with keys: allocation_id, dates, total_rows, su_types.
    """
    try:
        allocation = Allocation.objects.get(pk=allocation_id)
    except ObjectDoesNotExist as exc:
        raise CommandError(f"allocation id={allocation_id} not found") from exc

    base_usage = _parse_usage(su)
    if date:
        dates = [usage_models.validate_date_str(date)]
    elif current_month:
        month_str = _current_month_str()
        dates = dates_in_month(month_str)
        if through_today:
            today = date_type.today().isoformat()
            dates = [d for d in dates if d <= today]
    else:
        assert month is not None
        dates = dates_in_month(month)

    total_rows = 0
    for day_index, day in enumerate(dates):
        usage_info = usage_for_day(base_usage, day_index, ramp)
        _store_usage_in_database(allocation, day, usage_info)
        total_rows += len(usage_info.root)

    return {
        "allocation_id": allocation.id,
        "dates": dates,
        "total_rows": total_rows,
        "su_types": list(base_usage.keys()),
    }


class Command(BaseCommand):
    help = (
        "Insert test AllocationDailyBillableUsage rows for local development. "
        "Run from a ColdFront checkout with NERC local_settings (Option B)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--allocation-id",
            type=int,
            required=True,
            help="ColdFront allocation primary key",
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--date",
            help="Single day to seed (YYYY-MM-DD)",
        )
        group.add_argument(
            "--month",
            help="Seed every day in this month (YYYY-MM)",
        )
        group.add_argument(
            "--current-month",
            action="store_true",
            help=(
                "Seed every day in the current calendar month with 3 default SU types "
                "(OpenStack CPU, OpenStack V100 GPU, Storage)"
            ),
        )
        parser.add_argument(
            "--su",
            action="append",
            metavar="NAME=AMOUNT",
            help="SU type and charge; repeat to override the 3 defaults",
        )
        parser.add_argument(
            "--ramp",
            action="store_true",
            help="Increase each SU type slightly per day (chart-friendly)",
        )
        parser.add_argument(
            "--through-today",
            action="store_true",
            help="With --current-month, only seed days 1 through today (not future days)",
        )

    def handle(self, *args, **options):
        summary = seed_daily_billable_usage(
            allocation_id=options["allocation_id"],
            date=options.get("date"),
            month=options.get("month"),
            current_month=options.get("current_month", False),
            su=options.get("su"),
            ramp=options.get("ramp", False),
            through_today=options.get("through_today", False),
        )

        dates = summary["dates"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(summary['su_types'])} SU type(s) × {len(dates)} day(s) "
                f"= {summary['total_rows']} row(s) for allocation {summary['allocation_id']}"
            )
        )
        if len(dates) > 1:
            self.stdout.write(f"  dates: {dates[0]} … {dates[-1]}")
            for su_type in summary["su_types"]:
                self.stdout.write(f"  {su_type}")
        if len(dates) == 1:
            base_usage = _parse_usage(options.get("su"))
            for su_type, value in usage_for_day(
                base_usage, 0, options.get("ramp", False)
            ).root.items():
                self.stdout.write(f"  {dates[0]} {su_type}: {value}")


def _store_usage_in_database(allocation: Allocation, date: str, usage_info) -> None:
    for su_type, value in usage_info.root.items():
        AllocationDailyBillableUsage.objects.update_or_create(
            allocation=allocation,
            date=date,
            su_type=su_type,
            defaults={"value": value},
        )


def _parse_usage(su_args: list[str] | None) -> dict[str, str]:
    if not su_args:
        return dict(DEFAULT_USAGE)
    usage = {}
    for item in su_args:
        if "=" not in item:
            raise CommandError(
                f"expected NAME=AMOUNT, got {item!r} (e.g. 'OpenStack CPU=100.00')"
            )
        name, amount = item.split("=", 1)
        usage[name.strip()] = amount.strip()
    return usage
