RESOURCE_AUTH_URL = 'OpenStack Auth URL'  # TODO: remove OpenStack prefix
RESOURCE_FEDERATION_PROTOCOL = 'OpenStack Federation Protocol'
RESOURCE_IDP = 'OpenStack Identity Provider'
RESOURCE_PROJECT_DOMAIN = 'OpenStack Domain for Projects'
RESOURCE_ROLE = 'OpenStack Role for User in Project'
RESOURCE_USER_DOMAIN = 'OpenStack Domain for Users'
RESOURCE_DEFAULT_PUBLIC_NETWORK = 'OpenStack Public Network ID'
RESOURCE_DEFAULT_NETWORK_CIDR = 'OpenStack Default Network CIDR'

RESOURCE_ATTRIBUTES = [RESOURCE_AUTH_URL,
                       RESOURCE_FEDERATION_PROTOCOL,
                       RESOURCE_IDP,
                       RESOURCE_PROJECT_DOMAIN,
                       RESOURCE_ROLE,
                       RESOURCE_USER_DOMAIN,
                       RESOURCE_DEFAULT_PUBLIC_NETWORK,
                       RESOURCE_DEFAULT_NETWORK_CIDR]

# TODO: Migration to rename the OpenStack specific prefix out of these attrs
ALLOCATION_PROJECT_ID = 'OpenStack Project ID'
ALLOCATION_PROJECT_NAME = 'OpenStack Project Name'

ALLOCATION_ATTRIBUTES = [ALLOCATION_PROJECT_ID,
                         ALLOCATION_PROJECT_NAME]

###########################################################
# OpenStack Quota Attributes
QUOTA_INSTANCES = 'OpenStack Compute Instance Quota'
QUOTA_RAM = 'OpenStack Compute RAM Quota'
QUOTA_VCPU = 'OpenStack Compute vCPU Quota'

QUOTA_VOLUMES = 'OpenStack Volume Quota'
QUOTA_VOLUMES_GB = 'OpenStack Volume GB Quota'

QUOTA_FLOATING_IPS = 'OpenStack Floating IP Quota'

QUOTA_OBJECT_GB = 'OpenStack Swift Quota in Gigabytes'

QUOTA_GPU = 'OpenStack GPU Quota'

###########################################################
# OpenShift Quota Attributes
QUOTA_LIMITS_CPU = 'OpenShift Limit on CPU Quota'
QUOTA_LIMITS_MEMORY = 'OpenShift Limit on RAM Quota'
QUOTA_LIMITS_EPHEMERAL_STORAGE_GB = 'OpenShift Limit on Ephemeral Storage Quota (GB)'

ALLOCATION_QUOTA_ATTRIBUTES = [QUOTA_INSTANCES,
                               QUOTA_RAM,
                               QUOTA_VCPU,
                               QUOTA_VOLUMES,
                               QUOTA_VOLUMES_GB,
                               QUOTA_FLOATING_IPS,
                               QUOTA_OBJECT_GB,
                               QUOTA_GPU,
                               QUOTA_LIMITS_CPU,
                               QUOTA_LIMITS_MEMORY,
                               QUOTA_LIMITS_EPHEMERAL_STORAGE_GB]
