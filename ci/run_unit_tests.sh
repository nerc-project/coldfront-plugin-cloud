set -xe

if [[ ! "${CI}" == "true" ]]; then
    source /tmp/coldfront_venv/bin/activate
fi

export DJANGO_SETTINGS_MODULE="local_settings"

coverage run --source="." -a -m django test coldfront_plugin_cloud.tests.unit.test_attribute_migration
coverage run --source="." -a -m django test coldfront_plugin_cloud.tests.unit.test_calculate_quota_unit_hours
coverage run --source="." -a -m django test coldfront_plugin_cloud.tests.unit.test_utils
coverage report
