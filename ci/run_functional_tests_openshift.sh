# Creates the appropriate credentials and runs tests
#
# Tests expect the resource to be name Devstack
set -xe

if [[ ! "${CI}" == "true" ]]; then
    source /tmp/coldfront_venv/bin/activate
fi

export DJANGO_SETTINGS_MODULE="local_settings"
export FUNCTIONAL_TESTS="True"

export OS_AUTH_URL="https://onboarding-onboarding.cluster.local:6443"
export ACCT_MGT_IDENTITY_PROVIDER=developer #TODO: Replace this with resource attribute instead

export OPENSHIFT_MICROSHIFT_TOKEN="$(oc create token coldfront)"

coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.openshift
coverage report
