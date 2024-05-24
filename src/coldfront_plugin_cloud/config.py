from coldfront.config.base import INSTALLED_APPS
from coldfront.config.env import ENV
from coldfront.config.core import ALLOCATION_ATTRIBUTE_VIEW_LIST

if 'coldfront_plugin_cloud' not in INSTALLED_APPS:
    INSTALLED_APPS += [
        'coldfront_plugin_cloud',
    ]

if 'Allocated Project Name' not in ALLOCATION_ATTRIBUTE_VIEW_LIST:
    ALLOCATION_ATTRIBUTE_VIEW_LIST += [
        'Allocated Project Name'
    ]
