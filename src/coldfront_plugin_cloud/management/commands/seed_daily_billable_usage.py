import calendar
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from coldfront.core.allocation.models import Allocation
from coldfront_plugin_cloud import usage_models
from coldfront_plugin_cloud.management.commands.fetch_daily_billable_usage import (
    Command as FetchCommand,
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
        ramped[su_type] = str(float(amount) + day_index * step)
    return usage_models.UsageInfo(ramped)


def current_month() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"


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
        try:
            allocation = Allocation.objects.get(pk=options["allocation_id"])
        except Allocation.DoesNotExist as exc:
            raise CommandError(
                f"allocation id={options['allocation_id']} not found"
            ) from exc

        base_usage = self._parse_usage(options["su"])
        if options.get("date"):
            dates = [usage_models.validate_date_str(options["date"])]
        elif options.get("current_month"):
            month = current_month()
            dates = dates_in_month(month)
            if options["through_today"]:
                today = date.today().isoformat()
                dates = [d for d in dates if d <= today]
        else:
            dates = dates_in_month(options["month"])

        total_rows = 0
        for day_index, day in enumerate(dates):
            usage_info = usage_for_day(base_usage, day_index, options["ramp"])
            FetchCommand.store_usage_in_database(allocation, day, usage_info)
            total_rows += len(usage_info.root)

        su_count = len(base_usage)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {su_count} SU type(s) × {len(dates)} day(s) "
                f"= {total_rows} row(s) for allocation {allocation.id}"
            )
        )
        if len(dates) > 1:
            self.stdout.write(f"  dates: {dates[0]} … {dates[-1]}")
            for su_type in base_usage:
                self.stdout.write(f"  {su_type}")
        if len(dates) == 1:
            for su_type, value in usage_for_day(
                base_usage, 0, options["ramp"]
            ).root.items():
                self.stdout.write(f"  {dates[0]} {su_type}: {value}")

    @staticmethod
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
