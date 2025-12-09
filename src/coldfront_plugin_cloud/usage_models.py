import datetime
import functools
from decimal import Decimal
from typing import Annotated, TypeVar

import pydantic


def validate_date_str(v: str) -> str:
    datetime.datetime.strptime(v, "%Y-%m-%d")
    return v


def validate_month_str(v: str) -> str:
    datetime.datetime.strptime(v, "%Y-%m")
    return v


def get_invoice_month_from_date(date_str: str) -> str:
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m")


def is_date_same_month(date1_str: str, date2_str: str) -> bool:
    """Compares that two dates are within the same month."""
    return get_invoice_month_from_date(date1_str) == get_invoice_month_from_date(
        date2_str
    )


def to_dict(model):
    """Exports the pydantic model to dictionary format.

    The JSON mode argument ensures Decimals are converted to strings."""

    return model.model_dump(mode="json")


def merge_models(model1, model2):
    """Merges two instances of the same pydantic model."""
    if model1.__class__.__name__ == model2.__class__.__name__:
        return model1.__class__(to_dict(model1) | to_dict(model2))
    else:
        raise ValueError("Different types of models can't be merged.")


DateField = Annotated[str, pydantic.AfterValidator(validate_date_str)]
MonthField = Annotated[str, pydantic.AfterValidator(validate_month_str)]


class UsageInfo(pydantic.RootModel[dict[str, Decimal]]):
    @functools.cached_property
    def total_charges(self) -> Decimal:
        total = Decimal("0.00")
        for su_charge in self.root.values():
            total += su_charge
        return total


T = TypeVar("T", bound=str)


class ChargesDict(pydantic.RootModel[dict[T, UsageInfo]]):
    @functools.cached_property
    def most_recent_date(self) -> DateField:
        """Leverage lexical ordering of YYYY-MM-DD and YYYY-MM strings."""
        return max(self.root.keys()) if self.root else ""


class CumulativeChargesDict(ChargesDict[DateField]):
    @pydantic.model_validator(mode="after")
    def check_month(self):
        # Ensure all keys are in the same month
        if self.root:
            months = set()
            for date_str in self.root.keys():
                months.add(get_invoice_month_from_date(date_str))

            if len(months) != 1:
                raise ValueError("All dates must be within the same month")
        return self

    @functools.cached_property
    def total_charges(self) -> Decimal:
        total = Decimal("0.00")
        if most_recent_charges := self.root.get(self.most_recent_date):
            total = most_recent_charges.total_charges
        return total


class PreviousChargesDict(ChargesDict[MonthField]):
    @functools.cached_property
    def total_charges_by_su(self) -> dict[str, Decimal]:
        total = {}
        for usage_info in self.root.values():
            for su_name, charge in usage_info.root.items():
                total[su_name] = total.get(su_name, Decimal("0.00")) + charge
        return total

    @functools.cached_property
    def total_charges(self) -> Decimal:
        total = Decimal("0.00")
        for su_charge in self.total_charges_by_su.values():
            total += su_charge
        return total
