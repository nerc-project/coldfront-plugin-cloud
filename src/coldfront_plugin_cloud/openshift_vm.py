from coldfront_plugin_cloud import openshift


class OpenShiftVMResourceAllocator(openshift.OpenShiftResourceAllocator):
    resource_type = "openshift_vm"
