from typing import Dict

import pydantic
from pydantic import Field


class QuotaSpec(pydantic.BaseModel):
    """
    Fields:
    - quota_label: human readable label for the quota (must be unique across the dict)
    - multiplier: multiplier applied to the allocation quantity (int, >= 0)
    - static_quota: static extra quota added to every project (int, >= 0)
    - resource_type: type of resource (e.g. "storage" for storage quotas)
    - unit_suffix: textual unit suffix (e.g. "Gi", "Mi", "", etc.)
    """

    quota_label: str
    multiplier: int = Field(0, ge=0)
    static_quota: int = Field(0, ge=0)
    unit_suffix: str = ""
    resource_type: str = ""
    invoice_name: str = ""

    class Config:
        model_config = pydantic.ConfigDict(extra="ignore")

    def quota_by_su_quantity(self, quantity: int) -> int:
        """
        Compute the quota for a given SU quantity using the formula:
            quota = static_quota + multiplier * quantity
        """
        return self.static_quota + self.multiplier * int(quantity)

    def formatted_quota(self, quota_value: int) -> str:
        """
        Return the quota value with the unit_suffix appended as a string when a suffix is set.
        """
        return f"{quota_value}{self.unit_suffix}"


class QuotaSpecs(pydantic.RootModel[Dict[str, QuotaSpec]]):
    """
    Root model representing a mapping of display_name -> QuotaSpec.

    Validators:
    - Ensure quota_label values are unique across all QuotaSpec entries.
    """

    @pydantic.model_validator(mode="after")
    def validate_unique_labels(self):
        # Ensure quota_label values are unique across the dict
        labels = [q.quota_label for q in self.root.values()]
        if len(labels) != len(set(labels)):
            raise ValueError("Duplicate quota_label values found in QuotaSpecs")

        return self

    def get_quotas_by_type(self, resource_type: str) -> dict[str, QuotaSpec]:
        """
        Return a list of quota display names that are marked as storage types.
        """
        return {
            name: spec
            for name, spec in self.root.items()
            if spec.resource_type == resource_type
        }
