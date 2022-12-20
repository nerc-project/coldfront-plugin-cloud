# Cloud Plugin for ColdFront

The cloud plugin allows resource allocations to be requested and
provisioned in OpenStack and OpenShift cloud environments from ColdFront.

Note: OpenShift support requires deploying the [openshift-acct-mgt][]
API service.

[openshift-acct-mgt]: https://github.com/cci-moc/openshift-acct-mgt

## Terminology
Caution as OpenStack, OpenShift and ColdFront use the same term to mean different
things!
Those terms will be prefixed by the system they apply to.

### ColdFront
* resource - describes a computational environment for which access can be
  requested. In this document they will be referred to as
  **coldfront resources**.
* project - a container for grouping together metadata and resource
  allocations from the same group of people and for the same purpose.
  They will be referred as **coldfront projects**.
* resource allocation - tracks the lifecycle of access to an environment
  from a project.
* resource attribute - attributes associated to a specific environment.
* resource allocation attribute - attributes associated to a specific
  resource allocation on an environment from a project.

### OpenStack
* resource - describes a type of computational resource offered by
  the OpenStack cloud. In this document they will be referred to as
  **openstack resources**. Can be a virtual server, vCPUs, RAM, volumes, etc.
* project - OpenStack terminology for a resource allocation and all
  resource spawned therein. They will be referred as **openstack projects**.
* quota - limitation on the amount of a resource that can be consumed by a
  project.
* domain - container for groups and users. Allows some organizational
  and administrative separation.

### OpenShift
* project - OpenShift terminology for a namespace. In this document they
  will be referred to as **openshift projects**.

## Configuration
The plugin registers a helper command to register the appropriate resource
types and resource attribute types as described below. The cloud plugin
is called automatically for coldfront resources of type `OpenStack` and
`OpenShift`.

```bash
$ coldfront register_cloud_attributes
```

Multiple coldfront resources of type `OpenStack` or `OpenShift` can be created.

### Configuring for OpenStack

Authentication for OpenStack is loaded as pairs of environment variables in the form
`OPENSTACK_{resource_name}_APPLICATION_CREDENTIAL_ID` and
`OPENSTACK_{resource_name}_APPLICATION_CREDENTIAL_SECRET` where `{resource_name}`
is the name of the coldfront resource as all uppercase (with spaces and `-`
replaced by `_`).

Each OpenStack resource must have the following attributes set in coldfront:
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

Registration of OpenStack coldfront resources can be performed via the UI management
dashboard or through the helper command:

```bash
$ coldfront add_openstack_resource
usage: coldfront add_openstack_resource [-h] --name NAME --auth-url AUTH_URL [--users-domain USERS_DOMAIN] [--projects-domain PROJECTS_DOMAIN] --idp IDP
                                        [--protocol PROTOCOL] [--role ROLE] [--version] [-v {0,1,2,3}] [--settings SETTINGS] [--pythonpath PYTHONPATH] [--traceback]
                                        [--no-color] [--force-color]
coldfront add_openstack_resource: error: the following arguments are required: --name, --auth-url, --idp
```

### Configuring for OpenShift

Note: OpenShift support requires deploying the [openshift-acct-mgt][]
API service.

[openshift-acct-mgt]: https://github.com/cci-moc/openshift-acct-mgt

Authentication for OpenShift is loaded as pairs of environment variables
`OPENSHIFT_{resource_name}_USERNAME` and `OPENSHIFT_{resource_name}_PASSWORD`
where `{resource_name}` is the name of the coldfront resource as all uppercase
(with spaces and `-` replaced by `_`).

Each OpenShift resource must have the following attributes set in coldfront:
 * `OpenStack Auth URL` - the URL of the `openshift-acct-mgt` endpoint.
 * `OpenStack Role for User in Project` - the name of the `ClusterRole` to assign to users
   on the namespace.

Registration of OpenShift coldfront resources can be performed via the UI management
dashboard or through the helper command:

```bash
$ coldfront add_openshift_resource
usage: coldfront add_openshift_resource [-h] --name NAME --auth-url AUTH_URL [--role ROLE] [--version] [-v {0,1,2,3}] [--settings SETTINGS] [--pythonpath PYTHONPATH] [--traceback]
                                        [--no-color] [--force-color] [--skip-checks]
coldfront add_openshift_resource: error: the following arguments are required: --name, --auth-url
```

### Quotas

The amount of quota to start out a resource allocation after approval, can be
specified using an integer field in the resource allocation request form.

ColdFront has a current limitation on being able to display only one integer
field, therefore the concept of a **unit of computing** is introduced to tie
multiple resource quotas to a single multiplier.

| OpenStack Resource Name | Quota Amount x Unit |
|-------------------------|---------------------|
| Instances               | 1                   |
| vCPUs                   | 2                   |
| RAM                     | 4096                |
| Volumes                 | 1                   |

| OpenShift Resource Name               | Quota Amount x Unit |
|---------------------------------------|---------------------|
| Limit on CPU                          | 2                   |
| Limit on RAM (MB)                     | 2                   |
| Limit on Ephemeral Storage Quota (GB) | 5                   |

After the resource allocation has been approved, these resulting quota will be
stored individually per resource as resource allocation attributes under the
following resource allocation attribute types.

* OpenStack Compute Instance Quota
* OpenStack Compute RAM Quota
* OpenStack Compute vCPU Quota
* OpenStack Volumes Quota

* OpenShift Limit on CPU Quota
* OpenShift Limit on RAM Quota
* OpenShift Limit on Ephemeral Storage Quota (GB)

By submitting a Resource Allocation Change Request and editing those attributes
a PI can request a change in their quota.
