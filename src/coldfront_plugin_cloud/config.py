from coldfront.config.base import INSTALLED_APPS
from coldfront.config.env import ENV

for app in [
    'rest_framework',
    'rest_framework.authtoken',
    'coldfront_plugin_cloud',
]:
    if app not in INSTALLED_APPS:
        INSTALLED_APPS.append(app)
