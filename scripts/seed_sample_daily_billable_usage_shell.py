"""Seed AllocationDailyBillableUsage rows for local UI development.

Run from a ColdFront checkout with NERC local_settings:

    python manage.py shell < path/to/seed_daily_billable_usage_shell.py

Or from django shell:

    exec(open("path/to/seed_daily_billable_usage_shell.py").read())
"""

import calendar
from datetime import date as date_type
from decimal import Decimal

from coldfront.core.allocation.models import Allocation
from coldfront_plugin_cloud.models.daily_billable_usage import (
    AllocationDailyBillableUsage,
)

# --- configure before running ---
ALLOCATION_ID = 4

# Pick one date mode (set the others to None / False):
SINGLE_DATE = None  # YYYY-MM-DD, or None
MONTH = None  # YYYY-MM, or None
CURRENT_MONTH = True  # seed every day in the current calendar month
THROUGH_TODAY = True  # with CURRENT_MONTH, skip future days

RAMP = True  # increase each SU type slightly per day (chart-friendly)

DEFAULT_USAGE = {
    "OpenStack CPU": Decimal("100.00"),
    "OpenStack V100 GPU": Decimal("50.00"),
    "Storage": Decimal("30.12"),
}

_RAMP_STEP = {
    "OpenStack CPU": Decimal("5"),
    "OpenStack V100 GPU": Decimal("2"),
    "Storage": Decimal("0.5"),
}


def dates_in_month(month: str) -> list[str]:
    year, mon = map(int, month.split("-", 1))
    _, last_day = calendar.monthrange(year, mon)
    return [f"{year}-{mon:02d}-{day:02d}" for day in range(1, last_day + 1)]


def usage_for_day(
    base: dict[str, Decimal], day_index: int, ramp: bool
) -> dict[str, Decimal]:
    if not ramp:
        return dict(base)
    return {
        su_type: amount + _RAMP_STEP.get(su_type, Decimal("0")) * day_index
        for su_type, amount in base.items()
    }


def resolve_dates() -> list[str]:
    if SINGLE_DATE:
        return [SINGLE_DATE]
    if CURRENT_MONTH:
        today = date_type.today()
        month_str = f"{today.year}-{today.month:02d}"
        dates = dates_in_month(month_str)
        if THROUGH_TODAY:
            today_str = today.isoformat()
            dates = [d for d in dates if d <= today_str]
        return dates
    if MONTH:
        return dates_in_month(MONTH)
    raise ValueError("Set SINGLE_DATE, MONTH, or CURRENT_MONTH=True")


allocation = Allocation.objects.get(pk=ALLOCATION_ID)
dates = resolve_dates()
total_rows = 0

for day_index, day in enumerate(dates):
    for su_type, value in usage_for_day(DEFAULT_USAGE, day_index, RAMP).items():
        AllocationDailyBillableUsage.objects.update_or_create(
            allocation=allocation,
            date=day,
            su_type=su_type,
            defaults={"value": value},
        )
        total_rows += 1

print(
    f"Seeded {len(DEFAULT_USAGE)} SU type(s) × {len(dates)} day(s) "
    f"= {total_rows} row(s) for allocation {allocation.id}"
)
if len(dates) > 1:
    print(f"  dates: {dates[0]} … {dates[-1]}")
