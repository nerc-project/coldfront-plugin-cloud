# OpenStack Plugin for ColdFront

The OpenStack plugin allows resource allocations to be requested and
provisioned in OpenStack cloud environment from ColdFront.

## Terminology
Caution as OpenStack and ColdFront use the same term to mean different things!
Those terms will be prefixed by coldfront or openstack to specify which usage
they refer to.

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

## Configuration
The plugin registers a helper command to register the appropriate resource
types and resource attribute types as described below. The OpenStack plugin
is called automatically for coldfront resources of type `OpenStack`.

```bash
$ coldfront register_openstack_attributes
```

Multiple coldfront resources of type `OpenStack` can be created.
Authentication for each is loaded as pairs of environment variables in the form
`OPENSTACK_{resource_name}_APPLICATION_CREDENTIAL_ID` and
`OPENSTACK_{resource_name}_APPLICATION_CREDENTIAL_SECRET` where `{resource_name}`
is the name of the coldfront resource as all uppercase (with spaces and `-`
replaced by `_`).

Each coldfront resource must have the following attributes set:
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

### Quotas

The amount of quota to start out a resource allocation after approval, can be
specified using an integer field in the resource allocation request form.

ColdFront has a current limitation on being able to display only one integer
field, therefore the concept of a **unit of computing** is introduced to tie
multiple openstack resource quotas to a single multiplier.

| Resource Name  | Quota Amount x Unit |
| -------------- | ------------- |
| Instances  | 1  |
| vCPUs  | 2  |
| RAM | 4096 |
| Volumes | 1 |

After the resource allocation has been approved, these resulting quota will be
stored individually per resource as resource allocation attributes under the
following resource allocation attribute types.

* OpenStack Compute Instance Quota
* OpenStack Compute RAM Quota
* OpenStack Compute vCPU Quota
* OpenStack Volumes Quota

Currently, the plugin only supports setting the initial quota of a project.
However, these attributes are editable by an admin and in a future improvement
changes can be picked up by the plugin and re-synced with OpenStack. 
