import os
import pkgutil

from coldfront.config.settings import *
from django.conf import settings

plugin_openstack = pkgutil.get_loader('coldfront_plugin_cloud.config')

include(plugin_openstack.get_filename())


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}

if os.getenv('PLUGIN_OIDC') == 'True':
    REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'].append(
        'mozilla_django_oidc.contrib.drf.OIDCAuthentication',
    )
