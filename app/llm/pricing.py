"""Model price card (Slice 14a) — operator-supplied, fail-closed.

A price card maps an EXACT provider model id to its per-1k-token USD prices. The
shipped ``PRICE_CARD`` is intentionally **empty** — no fabricated model ids or prices.
An operator must register the exact configured model + its prices; an unpriced model
fails closed (``UnpricedModelError``) so the cost preflight can never be skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class UnpricedModelError(Exception):
    """Raised when no price-card entry exists for the configured model (fail closed)."""


@dataclass(frozen=True)
class ModelPrice:
    input_usd_per_1k: Decimal
    output_usd_per_1k: Decimal


# Operator-supplied. Empty by default — register exact provider model ids + prices here
# (or inject a card explicitly). No fabricated ids/prices ship in source.
PRICE_CARD: dict[str, ModelPrice] = {}


def get_price(model: str, price_card: dict[str, ModelPrice] | None = None) -> ModelPrice:
    card = PRICE_CARD if price_card is None else price_card
    price = card.get(model)
    if price is None:
        raise UnpricedModelError(f"no price-card entry for model {model!r}")
    return price
