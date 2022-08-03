from coldfront.core.allocation.models import (AllocationAttribute,
                                              AllocationAttributeType)


def env_safe_name(name):
    return name.replace(' ', '_').replace('-', '_').upper()


def set_attribute_on_allocation(allocation, attribute_type, attribute_value):
    allocation_attribute_type_obj = AllocationAttributeType.objects.get(
        name=attribute_type)
    try:
        attribute_obj = AllocationAttribute.objects.get(
            allocation_attribute_type=allocation_attribute_type_obj,
            allocation=allocation
        )
        attribute_obj.value = attribute_value
        attribute_obj.save()
    except AllocationAttribute.DoesNotExist:
        AllocationAttribute.objects.create(
            allocation_attribute_type=allocation_attribute_type_obj,
            allocation=allocation,
            value=attribute_value,
        )
