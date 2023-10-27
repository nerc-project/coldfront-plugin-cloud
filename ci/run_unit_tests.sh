set -xe

if [[ ! "${CI}" == "true" ]]; then
    source /tmp/coldfront_venv/bin/activate
fi

export DJANGO_SETTINGS_MODULE="local_settings"

coverage run --source="." -m django test coldfront_plugin_cloud.tests.unit
coverage report
