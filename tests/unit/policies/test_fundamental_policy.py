"""Unit tests for the directional fundamental baseline policy."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    FundamentalPolicy,
    InvalidPolicyError,
    MarketObservation,
    Side,
)


def obs(*, fundamental: str, mid: str | None) -> MarketObservation:
    return MarketObservation(
        step=0,
        instrument_id="ACME",
        fundamental_value=Decimal(fundamental),
        mid_price=None if mid is None else Decimal(mid),
    )


def test_fundamental_policy_buys_undervaluation_and_sells_overvaluation() -> None:
    policy = FundamentalPolicy(Decimal("2"), minimum_gap=Decimal("0.50"))
    assert policy.decide(obs(fundamental="101", mid="100"), agent_id="a").side is Side.BUY
    assert policy.decide(obs(fundamental="99", mid="100"), agent_id="a").side is Side.SELL


def test_fundamental_policy_holds_inside_dead_band_or_without_reference() -> None:
    policy = FundamentalPolicy(Decimal("2"), minimum_gap=Decimal("1"))
    assert policy.decide(obs(fundamental="100.5", mid="100"), agent_id="a").is_hold
    assert policy.decide(obs(fundamental="100", mid=None), agent_id="a").is_hold


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1")])
def test_fundamental_policy_rejects_non_positive_quantity(quantity: Decimal) -> None:
    with pytest.raises(InvalidPolicyError):
        FundamentalPolicy(quantity)
