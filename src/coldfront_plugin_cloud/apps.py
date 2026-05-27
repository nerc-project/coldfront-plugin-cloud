from django.apps import AppConfig


class OpenStackConfig(AppConfig):
    name = "coldfront_plugin_cloud"

    def ready(self):
        import coldfront_plugin_cloud.signals  # noqa: F401
        import coldfront_plugin_cloud.models.daily_billable_usage  # noqa: F401
