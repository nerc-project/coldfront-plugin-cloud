#!/bin/bash

# Creates the appropriate credentials and runs tests
#
# Tests expect the resource to be name Devstack
set -xe

export OPENSHIFT_MICROSHIFT_TOKEN="$(oc create token -n default test-serviceaccount)"
export OPENSHIFT_MICROSHIFT_VERIFY="false"

if [[ ! "${CI}" == "true" ]]; then
    source /tmp/coldfront_venv/bin/activate
fi

microshift_addr=$(sudo docker inspect microshift --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')

export DJANGO_SETTINGS_MODULE="local_settings"
export FUNCTIONAL_TESTS="True"
export OS_API_URL="https://$microshift_addr:6443"
export PYTHONWARNINGS="ignore:Unverified HTTPS request"


coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.openshift
coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.openshift_vm
coverage report
