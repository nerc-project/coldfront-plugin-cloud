#!/bin/bash

# Creates the appropriate credentials and runs tests
#
# Tests expect the resource to be name Devstack
set -xe

export OPENSHIFT_MICROSHIFT_USERNAME="admin"
export OPENSHIFT_MICROSHIFT_PASSWORD="pass"
export OPENSHIFT_MICROSHIFT_TOKEN="$(oc create token -n onboarding onboarding-serviceaccount)"
export OPENSHIFT_MICROSHIFT_VERIFY="false"

if [[ ! "${CI}" == "true" ]]; then
    source /tmp/coldfront_venv/bin/activate
fi

export DJANGO_SETTINGS_MODULE="local_settings"
export FUNCTIONAL_TESTS="True"
export OS_AUTH_URL="https://onboarding-onboarding.cluster.local"
export OS_API_URL="https://onboarding-onboarding.cluster.local:6443"


coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.openshift
coverage report
