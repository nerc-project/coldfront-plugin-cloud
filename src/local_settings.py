import pkgutil

from coldfront.config.settings import *  # noqa: F401, F403
from django.conf import settings  # noqa: F401

plugin_openstack = pkgutil.get_loader("coldfront_plugin_cloud.config")

include(plugin_openstack.get_filename())  # noqa: F405
