from collections.abc import Iterable

from coldfront.core.allocation.models import Allocation
from coldfront_plugin_cloud.models.daily_billable_usage import (
    AllocationDailyBillableUsage,
)
from coldfront_plugin_cloud.models.usage_models import UsageInfo, validate_date_str


def _rows_to_usage_info(rows: Iterable[AllocationDailyBillableUsage]) -> UsageInfo:
    """Build a UsageInfo from ORM rows (one row per SU type).

    Args:
        rows: AllocationDailyBillableUsage instances for a single allocation
            and date (or any set of rows to collapse into one dict).

    Returns:
        UsageInfo mapping SU type names to charge values. Empty when rows
        is empty.

    Raises:
        TypeError: If rows is None.
        ValueError: If a row has an empty su_type.

    Example:
        >>> rows = [
        ...     AllocationDailyBillableUsage(su_type="OpenStack CPU", value=100),
        ...     AllocationDailyBillableUsage(su_type="Storage", value=30.12),
        ... ]
        >>> info = _rows_to_usage_info(rows)
        >>> info.root["OpenStack CPU"]
        Decimal('100')
        >>> info.total_charges
        Decimal('130.12')
    """
    if rows is None:
        raise TypeError("rows must not be None")

    usage_info = UsageInfo({})
    for row in rows:
        if not isinstance(row, AllocationDailyBillableUsage):
            raise TypeError(
                f"each row must be AllocationDailyBillableUsage, got {type(row).__name__}"
            )
        if not row.su_type:
            raise ValueError(f"usage row id={row.pk} has empty su_type")
        usage_info.root[row.su_type] = row.value
    return usage_info


def get_daily_billable_usage(allocation: Allocation, date: str) -> UsageInfo:
    """Load billable usage for one allocation on one day.

    Args:
        allocation: ColdFront allocation whose daily_usage_records to read.
        date: Calendar day in ``YYYY-MM-DD`` format.

    Returns:
        UsageInfo for that allocation and date. Empty dict when no rows exist
        (no usage recorded yet for that day).

    Raises:
        TypeError: If allocation or date has the wrong type.
        ValueError: If allocation is unsaved, date is invalid, or empty.

    Example:
        >>> from coldfront_plugin_cloud.billable_usage import get_daily_billable_usage
        >>> usage = get_daily_billable_usage(allocation, "2025-11-15")
        >>> usage.root.get("OpenStack CPU")
        Decimal('100.00')
        >>> usage.total_charges  # sum of all SU types that day
        Decimal('180.12')
    """
    if not isinstance(allocation, Allocation):
        raise TypeError(
            f"allocation must be Allocation, got {type(allocation).__name__}"
        )
    if allocation.pk is None:
        raise ValueError("allocation must be saved (have a primary key)")
    if not isinstance(date, str) or not date.strip():
        raise ValueError("date must be a non-empty YYYY-MM-DD string")
    date = validate_date_str(date)

    rows = AllocationDailyBillableUsage.objects.filter(allocation=allocation, date=date)
    return _rows_to_usage_info(rows)


def get_daily_billable_usage_by_date(
    allocation: Allocation, start_date: str, end_date: str
) -> dict[str, UsageInfo]:
    """Load billable usage grouped by day across an inclusive date range.

    Args:
        allocation: ColdFront allocation to read.
        start_date: First day (inclusive), ``YYYY-MM-DD``.
        end_date: Last day (inclusive), ``YYYY-MM-DD``.

    Returns:
        Mapping of ``YYYY-MM-DD`` date strings to UsageInfo. Dates with no
        usage rows are omitted.

    Raises:
        TypeError: If allocation or either date has the wrong type.
        ValueError: If allocation is unsaved, a date is invalid, or
            start_date is after end_date.

    Example:
        >>> usage_by_date = get_daily_billable_usage_by_date(
        ...     allocation, "2025-11-01", "2025-11-30"
        ... )
        >>> usage_by_date["2025-11-15"].root
        {'OpenStack CPU': Decimal('100.00'), 'Storage': Decimal('30.12')}
    """
    if not isinstance(allocation, Allocation):
        raise TypeError(
            f"allocation must be Allocation, got {type(allocation).__name__}"
        )
    if allocation.pk is None:
        raise ValueError("allocation must be saved (have a primary key)")
    if not isinstance(start_date, str) or not start_date.strip():
        raise ValueError("start_date must be a non-empty YYYY-MM-DD string")
    if not isinstance(end_date, str) or not end_date.strip():
        raise ValueError("end_date must be a non-empty YYYY-MM-DD string")
    start_date = validate_date_str(start_date)
    end_date = validate_date_str(end_date)
    if start_date > end_date:
        raise ValueError(
            f"start_date {start_date} must be on or before end_date {end_date}"
        )

    rows = AllocationDailyBillableUsage.objects.filter(
        allocation=allocation,
        date__gte=start_date,
        date__lte=end_date,
    ).order_by("date", "su_type")

    usage_by_date: dict[str, UsageInfo] = {}
    for row in rows:
        day = row.date.isoformat() if hasattr(row.date, "isoformat") else str(row.date)
        usage_by_date.setdefault(day, UsageInfo({}))
        if not row.su_type:
            raise ValueError(f"usage row id={row.pk} has empty su_type")
        usage_by_date[day].root[row.su_type] = row.value

    return usage_by_date
