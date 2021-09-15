# Creates the appropriate credentials and runs tests
#
# Tests expect the resource to be name Devstack
openstack_cmd="microstack.openstack"
credential_name=$(openssl rand -base64 12)

export OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_SECRET=$(
    $openstack_cmd application credential create "$credential_name" -f value -c secret)
export OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_ID=$(
    $openstack_cmd application credential show "$credential_name" -f value -c id)

source /tmp/coldfront_venv/bin/activate

export DJANGO_SETTINGS_MODULE="local_settings"
export FUNCTIONAL_TESTS="True"

coldfront test coldfront_plugin_openstack.tests.functional

microstack.openstack application credential delete $OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_ID
