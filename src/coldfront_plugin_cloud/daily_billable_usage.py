from collections.abc import Iterable

from coldfront.core.allocation.models import Allocation
from coldfront_plugin_cloud.models.daily_billable_usage import AllocationDailyBillableUsage
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
        >>> from coldfront_plugin_cloud.daily_billable_usage import get_daily_billable_usage
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


def get_daily_billable_usage_range(
    allocation: Allocation, start_date: str, end_date: str
) -> UsageInfo:
    """Load billable usage rows for an allocation across an inclusive date range.

    Args:
        allocation: ColdFront allocation to read.
        start_date: First day (inclusive), ``YYYY-MM-DD``.
        end_date: Last day (inclusive), ``YYYY-MM-DD``.

    Returns:
        A single UsageInfo built from all matching rows. Each SU type appears
        at most once; if the same SU type exists on multiple days, the last
        row processed wins (queryset has no explicit ordering).

    Raises:
        TypeError: If allocation or either date has the wrong type.
        ValueError: If allocation is unsaved, a date is invalid, or
            start_date is after end_date.

    Note:
        For per-day breakdowns, call get_daily_billable_usage once per date
        or add a separate helper that returns a date-keyed structure
        (e.g. CumulativeChargesDict).

    Example:
        >>> usage = get_daily_billable_usage_range(
        ...     allocation, "2025-11-01", "2025-11-30"
        ... )
        >>> usage.root  # merged across the whole range, not per-day
        {'OpenStack CPU': Decimal('110.00'), 'Storage': Decimal('35.00')}
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
    )
    return _rows_to_usage_info(rows)
