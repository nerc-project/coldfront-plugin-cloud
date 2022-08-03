import pkgutil

from coldfront.config.settings import *
from django.conf import settings

plugin_openstack = pkgutil.get_loader('coldfront_plugin_cloud.config')

include(plugin_openstack.get_filename())
