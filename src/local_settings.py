import pkgutil

from coldfront.config.settings import *
from django.conf import settings

plugin_openstack = pkgutil.get_loader('coldfront_plugin_openstack.config')

include(plugin_openstack.get_filename())
