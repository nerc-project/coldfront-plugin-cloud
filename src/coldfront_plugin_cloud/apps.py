from django.apps import AppConfig


class OpenStackConfig(AppConfig):
    name = 'coldfront_plugin_cloud'

    def ready(self):
        import coldfront_plugin_cloud.signals
