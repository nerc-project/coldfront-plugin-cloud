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
                               end: datetime):
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
                if cr.history.first().created <= event_time:
                    if attr_cr := AllocationAttributeChangeRequest.objects.filter(
                        allocation_change_request=cr,
                        allocation_attribute=allocation_attribute,
                        new_value=event.value,
                    ).first():
                        break
            if not attr_cr:
                print(f"Couldn't find a matching changing request.")

        if attr_cr:
            # If a matching change request is found, we divide the time
            # between these two events into two and count the value.
            # Created may have happened in the previous billing cycle
            # which we need to ignore.
            created = cr.history.first().created
            if created < last_event_time:
                created = last_event_time

            print(f"Matching request: Last event at {last_event_time}, cr at"
                  f" {cr.history.first().created}, change at {event_time}")

            before = math.ceil((created - last_event_time).total_seconds())
            after = math.ceil((event_time - created).total_seconds())

            value_times_seconds += (before * last_event_value) + (after * int(event.value))
            print(f"Last event at {last_event_time}, cr created at {created}, approved at {event_time}")
        else:
            seconds_since_last_event = math.ceil((event_time - last_event_time).total_seconds())
            value_times_seconds += seconds_since_last_event * last_event_value

        last_event_time = event_time
        last_event_value = int(event.value)

    # The value remains the same from the last event until the end.
    since_last_event = math.ceil((end - last_event_time).total_seconds())
    value_times_seconds += since_last_event * last_event_value

    return math.ceil(value_times_seconds / 3600)
