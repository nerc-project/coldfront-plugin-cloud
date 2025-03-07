import os

from django.dispatch import receiver
from django_q.tasks import async_task

from coldfront_plugin_cloud.tasks import (activate_allocation,
                                          add_user_to_allocation,
                                          disable_allocation,
                                          remove_user_from_allocation,
                                          get_allocation_usage,
                                          approve_change_request)
from coldfront_plugin_cloud import utils
from coldfront.core.allocation.signals import (allocation_activate,
                                               allocation_activate_user,
                                               allocation_disable,
                                               allocation_remove_user,
                                               allocation_change_created,
                                               allocation_change_approved)


def is_async():
    # Note(knikolla): The presence of the REDIS_HOST env variable signifies
    # in `coldfront-nerc` the configuration of a Django Q cluster, therefore
    # execution is to be performed asynchronously for longer running tasks.
    return os.getenv('REDIS_HOST')


@receiver(allocation_activate)
@receiver(allocation_change_approved)
def activate_allocation_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')
    # Note(knikolla): Only run this task using Django-Q if a qcluster has
    # been configured.
    if is_async():
        async_task(activate_allocation, allocation_pk)
    else:
        activate_allocation(allocation_pk)


@receiver(allocation_disable)
def allocation_disable_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')
    disable_allocation(allocation_pk)


@receiver(allocation_activate_user)
def activate_allocation_user_receiver(sender, **kwargs):
    allocation_user_pk = kwargs.get('allocation_user_pk')
    if is_async():
        async_task(add_user_to_allocation, allocation_user_pk)
    else:
        add_user_to_allocation(allocation_user_pk)


@receiver(allocation_remove_user)
def allocation_remove_user_receiver(sender, **kwargs):
    allocation_user_pk = kwargs.get('allocation_user_pk')
    remove_user_from_allocation(allocation_user_pk)

# TODO (Quan): How to/should we do the functional test for this?
@receiver(allocation_change_created)
def allocation_change_created_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')
    allocation_change_pk = kwargs.get('allocation_change_pk')

    if not utils.check_cr_only_decreases(allocation_change_pk):
        return
    
    if utils.check_cr_set_to_zero(allocation_change_pk):
        return
    
    allocation_quota_usage = get_allocation_usage(allocation_pk)
    if allocation_quota_usage and utils.check_usage_is_lower(allocation_change_pk, allocation_quota_usage):
        approve_change_request(allocation_change_pk) # Updates attributes on Coldfront side
        allocation_change_approved.send(None, allocation_pk=allocation_pk, allocation_change_pk=allocation_change_pk)
