# OpenStack Plugin

## Configuration

The OpenStack plugin is fired automatically for resources of type `OpenStack`.

It expects the Resource to have the following attributes set:
 * `OpenStack Auth URL` - the URL of the Keystone endpoint (omitting version
   and ending slash)
 * `OpenStack Domain for Projects` - The domain id that new projects will be
   created in
 * `OpenStack Domain for Users` - The domain id that new users will be created in
 * `OpenStack Identity Provider` - The identity provider as configured in keystone
 * `OpenStack Federation Protocol` - (defaults to openid) The federation protocol
   used with the identity provider
 * `OpenStack Role for User in Project` - (defaults to member) The role name of
   the role that is assigned to the user on project creation

Authentication is done using application credentials. The application credential
is stored as the pair of environment variables in the form
`OPENSTACK_{resource_name}_APPLICATION_CREDENTIAL_ID` and
`OPENSTACK_{resource_name}_APPLICATION_CREDENTIAL_SECRET` where `{resource_name}`
is the all name of the resource as all uppercase (with spaces and `-` replaced by `_`).
