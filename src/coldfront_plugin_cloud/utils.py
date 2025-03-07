import dataclasses
import datetime
import math
import pytz
import re
import secrets

from coldfront.core.allocation.models import (Allocation,
                                              AllocationAttribute,
                                              AllocationAttributeType,
                                              AllocationChangeRequest,
                                              AllocationAttributeChangeRequest,)

from coldfront_plugin_cloud import attributes
from coldfront_plugin_cloud import openshift


def env_safe_name(name):
    return name.replace(' ', '_').replace('-', '_').upper()


def set_attribute_on_allocation(allocation, attribute_type, attribute_value):
    allocation_attribute_type_obj = AllocationAttributeType.objects.get(
        name=attribute_type)
    try:
        attribute_obj = AllocationAttribute.objects.get(
            allocation_attribute_type=allocation_attribute_type_obj,
            allocation=allocation
        )
        attribute_obj.value = attribute_value
        attribute_obj.save()
    except AllocationAttribute.DoesNotExist:
        AllocationAttribute.objects.create(
            allocation_attribute_type=allocation_attribute_type_obj,
            allocation=allocation,
            value=attribute_value,
        )

def get_unique_project_name(project_name, max_length=None):
    # The random hex at the end of the project name is 6 chars, 1 hyphen
    max_without_suffix = max_length - 7 if max_length else None
    return f'{project_name[:max_without_suffix]}-{secrets.token_hex(3)}'

def get_sanitized_project_name(project_name):
    '''
    Returns a sanitized project name that only contains lowercase
    alphanumeric characters and dashes (not leading or trailing.)
    '''
    project_name = project_name.lower()

    # replace special characters with dashes
    project_name = re.sub('[^a-z0-9-]', '-', project_name)

    # remove repeated and trailing dashes
    project_name = re.sub('-+', '-', project_name).strip('-')
    return project_name


def calculate_quota_unit_hours(allocation: Allocation,
                               attribute: str,
                               start: datetime,
                               end: datetime,
                               exclude_interval_list=None):
    """Returns unit*hours of quota allocated in a given period.

    Calculation is rounded up by the hour and tracks the history of change
    requests.

    :param allocation: Allocation object with the attribute to calculate.
    :param attribute: Name of the attribute to calculate.
    :param start: Start time to being calculation.
    :param end: End time for calculation.
    :return: Value of attribute * amount of hours.
    """

    allocation_attribute = AllocationAttribute.objects.filter(
        allocation_attribute_type__name=attribute,
        allocation = allocation
    ).first()
    if allocation_attribute is None:
        return 0
    value_history = list(allocation_attribute.history.all())
    value_history.reverse()

    # If project is not active, get last status change into
    # an unbilled status.
    unbilled_statuses = ["Denied", "Revoked"]
    if allocation.status.name in unbilled_statuses:
        for change in allocation.history.all():
            if change.status.name in unbilled_statuses:
                last_modified = change.modified
                break
        if last_modified <= start:
            return 0
        if last_modified < end:
            end = last_modified

    value_times_seconds = 0
    last_event_time = start
    unbounded_last_event_time = None

    last_event_value = 0
    for event in value_history:
        event_time = event.modified

        if event_time < start:
            event_time = start

        if end and event_time > end:
           event_time = end

        attr_cr = None
        # When a change request is made to decrease the value of a quota
        # attribute, we make the value effective for billing purposes at
        # the moment of creation, rather than approval.
        if int(event.value) < last_event_value:
            print(
                f"Value decreased from {last_event_value} to {event.value} in"
                f" {allocation.get_attribute(attributes.ALLOCATION_PROJECT_NAME)}")
            change_requests = AllocationChangeRequest.objects.filter(
                allocation=allocation,
                status__name = "Approved"
            ).order_by("-created")
            for cr in change_requests:
                # We start going backwards through the change requests until
                # find one that happened just before the next event.
                cr_created_at = cr.history.first().created
                if cr.history.first().created <= event_time:
                    if unbounded_last_event_time and unbounded_last_event_time > cr_created_at:
                        # But after the unbounded last event time.
                        continue

                    if attr_cr := AllocationAttributeChangeRequest.objects.filter(
                        allocation_change_request=cr,
                        allocation_attribute=allocation_attribute,
                        new_value=event.value,
                    ).first():
                        break
            if not attr_cr:
                print(f"Couldn't find a matching changing request.")

        if attr_cr:
            # If a matching change request (CR) is found, we divide the time
            # between these two events into two and count the value.
            # Created may have happened in the previous billing cycle
            # which we need to ignore.
            created = cr.history.first().created
            if created < last_event_time:
                created = last_event_time

            print(f"Matching request: Last event at {last_event_time}, cr at"
                  f" {cr.history.first().created}, change at {event_time}")

            before = get_included_duration(last_event_time, created, exclude_interval_list)
            after = get_included_duration(created, event_time, exclude_interval_list)

            value_times_seconds += (before * last_event_value) + (after * int(event.value))
            print(f"Last event at {last_event_time}, cr created at {created}, approved at {event_time}")
        else:
            seconds_since_last_event = get_included_duration(
                last_event_time, event_time, exclude_interval_list)
            value_times_seconds += seconds_since_last_event * last_event_value

        last_event_time = event_time
        unbounded_last_event_time = event.modified
        last_event_value = int(event.value)

    # The value remains the same from the last event until the end.
    since_last_event = get_included_duration(last_event_time, end, exclude_interval_list)
    value_times_seconds += since_last_event * last_event_value

    return math.ceil(value_times_seconds / 3600)

def load_excluded_intervals(excluded_interval_arglist):
    def interval_sort_key(e):
        return e[0]
    
    def check_overlapping_intervals(excluded_intervals_list):
        prev_interval = excluded_intervals_list[0]
        for i in range(1, len(excluded_intervals_list)): 
            cur_interval = excluded_intervals_list[i]
            assert cur_interval[0] >= prev_interval[1], \
            f"Interval start date {cur_interval[0]} overlaps with another interval's end date {prev_interval[1]}"
            prev_interval = cur_interval
    
    excluded_intervals_list = list()
    for interval in excluded_interval_arglist:
        start, end = interval.strip().split(",")
        start_dt, end_dt = [datetime.datetime.fromisoformat(i) for i in [start, end]]
        assert end_dt > start_dt, f"Interval end date ({end}) is before start date ({start})!"
        excluded_intervals_list.append(
            [
                pytz.utc.localize(datetime.datetime.fromisoformat(start)),
                pytz.utc.localize(datetime.datetime.fromisoformat(end))
            ] 
        )

    excluded_intervals_list.sort(key=interval_sort_key)
    check_overlapping_intervals(excluded_intervals_list)

    return excluded_intervals_list

def _clamp_time(time, min_time, max_time):
    if time < min_time:
        time = min_time
    if time > max_time:
        time = max_time
    return time


def get_included_duration(start: datetime.datetime, 
                          end: datetime.datetime, 
                          excluded_intervals):
    total_interval_duration = (end - start).total_seconds()
    if not excluded_intervals: 
        return total_interval_duration
    
    for e_interval_start, e_interval_end in excluded_intervals:
        e_interval_start = _clamp_time(e_interval_start, start, end)
        e_interval_end = _clamp_time(e_interval_end, start, end)
        total_interval_duration -= (e_interval_end - e_interval_start).total_seconds()

    return math.ceil(total_interval_duration)


def parse_openshift_quota_value(attr_name, quota_value):
    PATTERN = r"([0-9]+)(m|Ki|Mi|Gi|Ti|Pi|Ei|K|M|G|T|P|E)?"

    suffix = {
        "Ki": 2**10,
        "Mi": 2**20,
        "Gi": 2**30,
        "Ti": 2**40,
        "Pi": 2**50,
        "Ei": 2**60,
        "m": 10**-3,
        "K": 10**3,
        "M": 10**6,
        "G": 10**9,
        "T": 10**12,
        "P": 10**15,
        "E": 10**18,
    }

    if quota_value and quota_value != "0":
        result = re.search(PATTERN, quota_value)

        if result is None:
            raise ValueError(
                f"Unable to parse quota_value = '{quota_value}' for {attr_name}"
            )

        value = int(result.groups()[0])
        unit = result.groups()[1]

        # Convert to number i.e. without any unit suffix

        if unit is not None:
            quota_value = value * suffix[unit]
        else:
            quota_value = value

        # Convert some attributes to units that coldfront uses

        if "RAM" in attr_name:
            return round(quota_value / suffix["Mi"])
        elif "Storage" in attr_name:
            return round(quota_value / suffix["Gi"])
        return quota_value
    elif quota_value and quota_value == "0":
        return 0


def check_if_quota_attr(attr_name):
    for quota_attr in attributes.ALLOCATION_QUOTA_ATTRIBUTES:
        if attr_name == quota_attr.name:
            return True
    return False


def check_cr_only_decreases(allocation_change_pk):
    """Checks if the change request only decreases the quota.

    :param allocation_change_pk: key of AllocationChangeRequest object.
    :return: True if the change request only decreases the quota.
    """
    allocation_cr = AllocationChangeRequest.objects.get(pk=allocation_change_pk)
    allocation_attr_cr_list = AllocationAttributeChangeRequest.objects.filter(
        allocation_change_request=allocation_cr
    )

    for allocation_attr_cr in allocation_attr_cr_list:
        attr_name = allocation_attr_cr.allocation_attribute.allocation_attribute_type.name
        if check_if_quota_attr(attr_name):
            if int(allocation_attr_cr.new_value) > int(allocation_attr_cr.allocation_attribute.value):
                return False
    return True


def check_cr_set_to_zero(allocation_change_pk):
    """Checks if the change request only decreases the quota.

    :param allocation_change_pk: key of AllocationChangeRequest object.
    :return: True if the change request only decreases the quota.
    """
    allocation_cr = AllocationChangeRequest.objects.get(pk=allocation_change_pk)
    allocation_attr_cr_list = AllocationAttributeChangeRequest.objects.filter(
        allocation_change_request=allocation_cr
    )

    for allocation_attr_cr in allocation_attr_cr_list:
        attr_name = allocation_attr_cr.allocation_attribute.allocation_attribute_type.name
        if check_if_quota_attr(attr_name):
            if int(allocation_attr_cr.new_value) == 0:
                return True
    return False


def check_usage_is_lower(allocation_change_pk, allocation_quota_usage):
    """Checks if the usage is lower than the quota.

    :param allocation_change_pk: AllocationChangeRequest object.
    :param allocation_quota_usage: Quota usage to compare.
    :return: True if the usage is lower than the quota.
    """
    allocation_cr = AllocationChangeRequest.objects.get(pk=allocation_change_pk)
    allocation_attr_cr_list = AllocationAttributeChangeRequest.objects.filter(
        allocation_change_request=allocation_cr
    )

    for allocation_attr_cr in allocation_attr_cr_list:
        attr_name = allocation_attr_cr.allocation_attribute.allocation_attribute_type.name
        if check_if_quota_attr(attr_name):
            # TODO (Quan) Copied from `validate_allocations`, I feel like this is very messy 
            quota_key_with_lambda = openshift.QUOTA_KEY_MAPPING.get(attr_name, None)
            quota_key = list(quota_key_with_lambda(1).keys())[0]                
            if int(allocation_attr_cr.new_value) < parse_openshift_quota_value(attr_name, allocation_quota_usage[quota_key]):
                return False
    return True
    
    
