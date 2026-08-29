from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ProductPricingPolicy:
    """Resolve one configured amount per agent SKU with an optional fallback.

    A SKU present in ``sku_amounts`` always wins over ``default_amount``. A
    ``None`` override intentionally leaves that SKU unpriced even when a default
    amount is configured.
    """

    default_amount: Decimal | None = None
    currency: str = "USD"
    sku_amounts: Mapping[str, Decimal | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        currency = self.currency.upper()
        if len(currency) != 3:
            raise ValueError("agent price currency must be a three-letter code")
        _validate_amount(self.default_amount, "default")
        normalized: dict[str, Decimal | None] = {}
        for sku, amount in self.sku_amounts.items():
            if not sku:
                raise ValueError("agent SKU price override cannot use an empty SKU")
            _validate_amount(amount, sku)
            normalized[sku] = amount
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "sku_amounts", normalized)

    def amount_for(self, sku: str) -> Decimal | None:
        if sku in self.sku_amounts:
            return self.sku_amounts[sku]
        return self.default_amount


def normalized_decimal(value: Decimal) -> str:
    """Return a stable non-exponent decimal string for payment identities."""

    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _validate_amount(amount: Decimal | None, label: str) -> None:
    if amount is not None and amount < 0:
        raise ValueError(f"agent price for {label} cannot be negative")
