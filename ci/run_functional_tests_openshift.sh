# Creates the appropriate credentials and runs tests
#
# Tests expect the resource to be name Devstack
set -xe

export OPENSHIFT_MICROSHIFT_USERNAME="admin"
export OPENSHIFT_MICROSHIFT_PASSWORD="pass"

source /tmp/coldfront_venv/bin/activate

export DJANGO_SETTINGS_MODULE="local_settings"
export FUNCTIONAL_TESTS="True"
export OS_AUTH_URL="https://onboarding-onboarding.cluster.local"

coldfront test coldfront_plugin_openstack.tests.functional.openshift
