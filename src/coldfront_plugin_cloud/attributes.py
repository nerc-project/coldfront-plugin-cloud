from dataclasses import dataclass


@dataclass
class CloudResourceAttribute:
    """Class for configuring Cloud Resource Attributes"""

    name: str
    type: str = "Text"


@dataclass
class CloudAllocationAttribute:
    """Class for configuring Cloud Allocation Attributes"""

    name: str
    type: str = "Int"
    has_usage: bool = False
    is_private: bool = False
    is_changeable: bool = True


RESOURCE_AUTH_URL = "Identity Endpoint URL"
RESOURCE_API_URL = "OpenShift API Endpoint URL"
RESOURCE_IDENTITY_NAME = "OpenShift Identity Provider Name"
RESOURCE_ROLE = "Role for User in Project"
RESOURCE_IBM_AVAILABLE = "IBM Spectrum Scale Storage Available"

RESOURCE_FEDERATION_PROTOCOL = "OpenStack Federation Protocol"
RESOURCE_IDP = "OpenStack Identity Provider"
RESOURCE_PROJECT_DOMAIN = "OpenStack Domain for Projects"
RESOURCE_USER_DOMAIN = "OpenStack Domain for Users"
RESOURCE_DEFAULT_PUBLIC_NETWORK = "OpenStack Public Network ID"
RESOURCE_DEFAULT_NETWORK_CIDR = "OpenStack Default Network CIDR"

RESOURCE_EULA_URL = "EULA URL"
RESOURCE_CLUSTER_NAME = "Internal Cluster Name"

RESOURCE_ATTRIBUTES = [
    CloudResourceAttribute(name=RESOURCE_AUTH_URL),
    CloudResourceAttribute(name=RESOURCE_API_URL),
    CloudResourceAttribute(name=RESOURCE_IDENTITY_NAME),
    CloudResourceAttribute(name=RESOURCE_FEDERATION_PROTOCOL),
    CloudResourceAttribute(name=RESOURCE_IDP),
    CloudResourceAttribute(name=RESOURCE_PROJECT_DOMAIN),
    CloudResourceAttribute(name=RESOURCE_ROLE),
    CloudResourceAttribute(name=RESOURCE_IBM_AVAILABLE),
    CloudResourceAttribute(name=RESOURCE_USER_DOMAIN),
    CloudResourceAttribute(name=RESOURCE_EULA_URL),
    CloudResourceAttribute(name=RESOURCE_DEFAULT_PUBLIC_NETWORK),
    CloudResourceAttribute(name=RESOURCE_DEFAULT_NETWORK_CIDR),
    CloudResourceAttribute(name=RESOURCE_CLUSTER_NAME),
]

# TODO: Migration to rename the OpenStack specific prefix out of these attrs
ALLOCATION_PROJECT_ID = "Allocated Project ID"
ALLOCATION_PROJECT_NAME = "Allocated Project Name"
ALLOCATION_INSTITUTION_SPECIFIC_CODE = "Institution-Specific Code"
ALLOCATION_CUMULATIVE_CHARGES = "Cumulative Daily Charges for Month"
ALLOCATION_PREVIOUS_CHARGES = "Previous Charges"
ALLOCATION_ALERT = "Monthly Allocation Cost Alert"

ALLOCATION_ATTRIBUTES = [
    CloudAllocationAttribute(
        name=ALLOCATION_PROJECT_ID, type="Text", is_changeable=False
    ),
    CloudAllocationAttribute(
        name=ALLOCATION_PROJECT_NAME, type="Text", is_changeable=False
    ),
    CloudAllocationAttribute(
        name=ALLOCATION_INSTITUTION_SPECIFIC_CODE, type="Text", is_changeable=True
    ),
    CloudAllocationAttribute(
        name=ALLOCATION_CUMULATIVE_CHARGES,
        type="Text",
        is_private=True,
        is_changeable=True,
    ),
    CloudAllocationAttribute(
        name=ALLOCATION_PREVIOUS_CHARGES,
        type="Text",
        is_private=True,
        is_changeable=True,
    ),
    CloudAllocationAttribute(name=ALLOCATION_ALERT, type="Int", is_changeable=True),
]

###########################################################
# OpenStack Quota Attributes
QUOTA_INSTANCES = "OpenStack Compute Instance Quota"
QUOTA_RAM = "OpenStack Compute RAM Quota (MiB)"
QUOTA_VCPU = "OpenStack Compute vCPU Quota"

QUOTA_VOLUMES = "OpenStack Number of Volumes Quota"
QUOTA_VOLUMES_GB = "OpenStack Volume Quota (GiB)"

QUOTA_FLOATING_IPS = "OpenStack Floating IP Quota"
QUOTA_NETWORKS = "Openstack Network Quota"

QUOTA_OBJECT_GB = "OpenStack Swift Quota (GiB)"

QUOTA_GPU = "OpenStack GPU Quota"

###########################################################
# OpenShift Quota Attributes
QUOTA_LIMITS_CPU = "OpenShift Limit on CPU Quota"
QUOTA_LIMITS_MEMORY = "OpenShift Limit on RAM Quota (MiB)"
QUOTA_LIMITS_EPHEMERAL_STORAGE_GB = "OpenShift Limit on Ephemeral Storage Quota (GiB)"
QUOTA_REQUESTS_NESE_STORAGE = "OpenShift Request on NESE Storage Quota (GiB)"
QUOTA_REQUESTS_IBM_STORAGE = "OpenShift Request on IBM Storage Quota (GiB)"
QUOTA_REQUESTS_GPU = "OpenShift Request on GPU Quota"
QUOTA_REQUESTS_VM_GPU_A100_SXM4 = "OpenShift Request on GPU A100 SXM4"
QUOTA_REQUESTS_VM_GPU_V100 = "OpenShift Request on GPU V100"
QUOTA_REQUESTS_VM_GPU_H100 = "OpenShift Request on GPU H100"
QUOTA_PVC = "OpenShift Persistent Volume Claims Quota"


ALLOCATION_QUOTA_ATTRIBUTES = [
    CloudAllocationAttribute(name=QUOTA_INSTANCES),
    CloudAllocationAttribute(name=QUOTA_RAM),
    CloudAllocationAttribute(name=QUOTA_VCPU),
    CloudAllocationAttribute(name=QUOTA_VOLUMES),
    CloudAllocationAttribute(name=QUOTA_VOLUMES_GB),
    CloudAllocationAttribute(name=QUOTA_NETWORKS),
    CloudAllocationAttribute(name=QUOTA_FLOATING_IPS),
    CloudAllocationAttribute(name=QUOTA_OBJECT_GB),
    CloudAllocationAttribute(name=QUOTA_GPU),
    CloudAllocationAttribute(name=QUOTA_LIMITS_CPU),
    CloudAllocationAttribute(name=QUOTA_LIMITS_MEMORY),
    CloudAllocationAttribute(name=QUOTA_LIMITS_EPHEMERAL_STORAGE_GB),
    CloudAllocationAttribute(name=QUOTA_REQUESTS_NESE_STORAGE),
    CloudAllocationAttribute(name=QUOTA_REQUESTS_IBM_STORAGE),
    CloudAllocationAttribute(name=QUOTA_REQUESTS_GPU),
    CloudAllocationAttribute(name=QUOTA_REQUESTS_VM_GPU_A100_SXM4),
    CloudAllocationAttribute(name=QUOTA_REQUESTS_VM_GPU_V100),
    CloudAllocationAttribute(name=QUOTA_REQUESTS_VM_GPU_H100),
    CloudAllocationAttribute(name=QUOTA_PVC),
]
