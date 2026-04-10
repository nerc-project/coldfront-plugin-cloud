#!/bin/bash
set -xe

if [[ ! "${CI}" == "true" ]]; then
    source /tmp/coldfront_venv/bin/activate
fi

export DJANGO_SETTINGS_MODULE="local_settings"
export PYTHONWARNINGS="ignore:Unverified HTTPS request"

export KEYCLOAK_BASE_URL="http://localhost:8080"
export KEYCLOAK_REALM="master"
export KEYCLOAK_CLIENT_ID="coldfront"
export KEYCLOAK_CLIENT_SECRET="nomoresecret"

coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.keycloak
coverage report
