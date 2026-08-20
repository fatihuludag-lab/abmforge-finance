"""Unit tests for immutable policy-facing market observations."""

from decimal import Decimal

import pytest

from abmforge_finance import InvalidObservationError, MarketObservation


def observation(**overrides: object) -> MarketObservation:
    values: dict[str, object] = {
        "step": 3,
        "instrument_id": "ACME",
        "fundamental_value": Decimal("101"),
        "best_bid": Decimal("99"),
        "best_ask": Decimal("101"),
        "mid_price": Decimal("100"),
        "spread": Decimal("2"),
        "bid_depth": Decimal("12"),
        "ask_depth": Decimal("8"),
        "imbalance": Decimal("0.2"),
        "last_trade_price": Decimal("100.5"),
        "price_change": Decimal("0.5"),
        "cash": Decimal("1000"),
        "inventory": Decimal("7"),
    }
    values.update(overrides)
    return MarketObservation(**values)  # type: ignore[arg-type]


def test_reference_price_uses_deterministic_fallback_order() -> None:
    assert observation().reference_price == Decimal("100")
    assert observation(mid_price=None).reference_price == Decimal("100.5")
    assert observation(mid_price=None, last_trade_price=None).reference_price == Decimal("99")
    assert observation(
        mid_price=None, last_trade_price=None, best_bid=None
    ).reference_price == Decimal("101")
    assert (
        observation(
            mid_price=None,
            last_trade_price=None,
            best_bid=None,
            best_ask=None,
        ).reference_price
        is None
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("step", -1),
        ("fundamental_value", Decimal("0")),
        ("bid_depth", Decimal("-1")),
        ("ask_depth", Decimal("-1")),
        ("imbalance", Decimal("1.1")),
    ],
)
def test_invalid_observation_values_are_rejected(field: str, value: object) -> None:
    with pytest.raises(InvalidObservationError):
        observation(**{field: value})


def test_crossed_best_quotes_are_rejected() -> None:
    with pytest.raises(InvalidObservationError, match="best_bid must be less than best_ask"):
        observation(best_bid=Decimal("101"), best_ask=Decimal("100"))
