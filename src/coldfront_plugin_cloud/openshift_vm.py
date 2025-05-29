from coldfront_plugin_cloud import attributes, openshift


class OpenShiftVMResourceAllocator(openshift.OpenShiftResourceAllocator):
    QUOTA_KEY_MAPPING = {
        attributes.QUOTA_LIMITS_CPU: lambda x: {"limits.cpu": f"{x * 1000}m"},
        attributes.QUOTA_LIMITS_MEMORY: lambda x: {"limits.memory": f"{x}Mi"},
        attributes.QUOTA_LIMITS_EPHEMERAL_STORAGE_GB: lambda x: {
            "limits.ephemeral-storage": f"{x}Gi"
        },
        attributes.QUOTA_REQUESTS_STORAGE: lambda x: {"requests.storage": f"{x}Gi"},
        attributes.QUOTA_REQUESTS_VM_GPU_A100_SXM4: lambda x: {
            "requests.nvidia.com/A100_SXM4_40GB": f"{x}"
        },
        attributes.QUOTA_REQUESTS_VM_GPU_V100: lambda x: {
            "requests.nvidia.com/GV100GL_Tesla_V100": f"{x}"
        },
        attributes.QUOTA_REQUESTS_VM_GPU_H100: lambda x: {
            "requests.nvidia.com/H100_SXM5_80GB": f"{x}"
        },
        attributes.QUOTA_PVC: lambda x: {"persistentvolumeclaims": f"{x}"},
    }

    resource_type = "openshift_vm"
