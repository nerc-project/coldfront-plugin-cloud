#!/bin/bash

# Creates the appropriate credentials and runs tests
#
# Tests expect the resource to be name Devstack
set -xe

export CREDENTIAL_NAME=$(openssl rand -base64 12)

export OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_SECRET=$(
  microstack.openstack application credential create "$CREDENTIAL_NAME" -f value -c secret)
export OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_ID=$(
  microstack.openstack application credential show "$CREDENTIAL_NAME" -f value -c id)

export OPENSTACK_ESI_APPLICATION_CREDENTIAL_SECRET=$OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_SECRET
export OPENSTACK_ESI_APPLICATION_CREDENTIAL_ID=$OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_ID

export OPENSTACK_PUBLIC_NETWORK_ID=$(microstack.openstack network show external -f value -c id)
export DJANGO_SETTINGS_MODULE="local_settings"
export FUNCTIONAL_TESTS="True"
export OS_AUTH_URL="https://localhost:5000"

coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.openstack
coverage run --source="." -m django test coldfront_plugin_cloud.tests.functional.esi
coverage report

microstack.openstack application credential delete $OPENSTACK_DEVSTACK_APPLICATION_CREDENTIAL_ID
