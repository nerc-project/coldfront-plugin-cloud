# Creates the appropriate credentials and runs tests
#
# Tests expect the resource to be name Devstack

source /opt/stack/devstack-plugin-oidc/tools/config.sh
source /opt/stack/devstack/openrc admin admin

credential_name=$(openssl rand -base64 12)

export OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_SECRET=$(
    openstack application credential create "$credential_name" -f value -c secret)
export OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_ID=$(
    openstack application credential show "$credential_name" -f value -c id)

source /tmp/coldfront_venv/bin/activate

export DJANGO_SETTINGS_MODULE="local_settings"
export FUNCTIONAL_TESTS="True"
export OS_AUTH_URL="http://$HOST_IP/identity"
export KEYCLOAK_URL="http://$HOST_IP:8080"
export KEYCLOAK_USER="admin"
export KEYCLOAK_PASS="nomoresecret"
export KEYCLOAK_REALM="master"
export OIDC_RP_CLIENT_ID="devstack"
export OIDC_RP_CLIENT_SECRET="nomoresecret"
export OIDC_REDIRECT_URI="http://$HOST_IP/identity/v3/auth/OS-FEDERATION/identity_providers/sso/protocols/openid/websso"

coldfront test coldfront_plugin_openstack.tests.functional

openstack application credential delete $OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_ID
