import os

from django.dispatch import receiver
from django_q.tasks import async_task

from coldfront_plugin_openstack.tasks import (activate_allocation,
                                              add_user_to_allocation,
                                              disable_allocation,
                                              remove_user_from_allocation)
from coldfront.core.allocation.signals import (allocation_activate,
                                               allocation_activate_user,
                                               allocation_disable,
                                               allocation_remove_user)


@receiver(allocation_activate)
def activate_allocation_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')
    # Note(knikolla): Only run this task using Django-Q if a qcluster has
    # been configured.
    if os.getenv('REDIS_HOST'):
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
    add_user_to_allocation(allocation_user_pk)


@receiver(allocation_remove_user)
def allocation_remove_user_receiver(sender, **kwargs):
    allocation_user_pk = kwargs.get('allocation_user_pk')
    remove_user_from_allocation(allocation_user_pk)
