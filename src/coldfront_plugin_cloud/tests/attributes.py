from coldfront_plugin_cloud.attributes import *  # noqa: F403


# OpenStack Quota Attributes
QUOTA_INSTANCES = "OpenStack Compute Instance Quota"
QUOTA_RAM = "OpenStack Compute RAM Quota (MiB)"
QUOTA_VCPU = "OpenStack Compute vCPU Quota"

QUOTA_VOLUMES = "OpenStack Number of Volumes Quota"
QUOTA_VOLUMES_GB = "OpenStack Volume Quota (GiB)"

QUOTA_FLOATING_IPS = "OpenStack Floating IP Quota"
QUOTA_NETWORKS = "Openstack Network Quota"

QUOTA_OBJECT_GB = "OpenStack Swift Quota (GiB)"

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
