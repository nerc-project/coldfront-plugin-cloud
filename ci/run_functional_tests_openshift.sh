#!/bin/bash

# Creates the appropriate credentials and runs tests
#
# Tests expect the resource to be name Devstack
set -xe

export KEYCLOAK_BASE_URL="http://localhost:8080"
export KEYCLOAK_REALM="master"
export KEYCLOAK_CLIENT_ID="admin-cli"
export KEYCLOAK_ADMIN_USER="admin"
export KEYCLOAK_ADMIN_PASSWORD="nomoresecret"

export OPENSHIFT_MICROSHIFT_TOKEN="$(oc create token -n onboarding onboarding-serviceaccount)"
export OPENSHIFT_MICROSHIFT_VERIFY="false"

if [[ ! "${CI}" == "true" ]]; then
    source /tmp/coldfront_venv/bin/activate
fi

export DJANGO_SETTINGS_MODULE="local_settings"
export FUNCTIONAL_TESTS="True"
export OS_API_URL="https://onboarding-onboarding.cluster.local:6443"
export PYTHONWARNINGS="ignore:Unverified HTTPS request"


coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.openshift
coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.openshift_vm
coverage report
