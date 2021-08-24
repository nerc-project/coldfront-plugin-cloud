from coldfront.core.allocation.models import (AllocationAttribute,
                                              AllocationAttributeType)


def add_attribute_to_allocation(allocation, attribute_type, attribute_value):
    allocation_attribute_type_obj = AllocationAttributeType.objects.get(
        name=attribute_type)
    AllocationAttribute.objects.create(
        allocation_attribute_type=allocation_attribute_type_obj,
        allocation=allocation,
        value=attribute_value,
    )
