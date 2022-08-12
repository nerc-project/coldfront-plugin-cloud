import os
import traceback

from django.dispatch import receiver
from django_q.tasks import async_task

from coldfront_plugin_cloud.tasks import (activate_allocation,
                                          add_user_to_allocation,
                                          disable_allocation,
                                          remove_user_from_allocation)
from coldfront.core.allocation.signals import (allocation_activate,
                                               allocation_activate_user,
                                               allocation_disable,
                                               allocation_remove_user,
                                               allocation_change_approved)
from coldfront.core.utils.mail import send_email
from coldfront.core.utils.common import import_from_settings

EMAIL_ENABLED = import_from_settings('EMAIL_ENABLED', False)
if EMAIL_ENABLED:
    EMAIL_SENDER = import_from_settings('EMAIL_SENDER')
    EMAIL_ADMIN_LIST = import_from_settings('EMAIL_ADMIN_LIST')


def is_async():
    # Note(knikolla): The presence of the REDIS_HOST env variable signifies
    # in `coldfront-nerc` the configuration of a Django Q cluster, therefore
    # execution is to be performed asynchronously for longer running tasks.
    return os.getenv('REDIS_HOST')


def run_fuction_and_email_on_error(func, *args):
    try:
        func(*args)
    except Exception as e:
        if EMAIL_ENABLED:
            send_email(
                "Error running task",
                traceback.format_exc(),
                EMAIL_SENDER,
                [EMAIL_ADMIN_LIST]
            )
        raise e


@receiver(allocation_activate)
@receiver(allocation_change_approved)
def activate_allocation_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')
    # Note(knikolla): Only run this task using Django-Q if a qcluster has
    # been configured.
    if is_async():
        async_task(run_fuction_and_email_on_error, activate_allocation, allocation_pk)
    else:
        run_fuction_and_email_on_error(activate_allocation, allocation_pk)


@receiver(allocation_disable)
def allocation_disable_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')
    run_fuction_and_email_on_error(disable_allocation, allocation_pk)


@receiver(allocation_activate_user)
def activate_allocation_user_receiver(sender, **kwargs):
    allocation_user_pk = kwargs.get('allocation_user_pk')
    if is_async():
        async_task(
            run_fuction_and_email_on_error, add_user_to_allocation, allocation_user_pk
        )
    else:
        run_fuction_and_email_on_error(add_user_to_allocation, allocation_user_pk)


@receiver(allocation_remove_user)
def allocation_remove_user_receiver(sender, **kwargs):
    allocation_user_pk = kwargs.get('allocation_user_pk')
    run_fuction_and_email_on_error(remove_user_from_allocation, allocation_user_pk)
