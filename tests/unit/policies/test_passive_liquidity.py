"""Unit tests for the deterministic passive-liquidity baseline."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    InvalidPolicyError,
    MarketObservation,
    PassiveLiquidityPolicy,
    Side,
    TimeInForce,
)


def _obs(step: int = 0, fundamental: str = "100") -> MarketObservation:
    return MarketObservation(
        step=step,
        instrument_id="ACME",
        fundamental_value=Decimal(fundamental),
    )


def test_exact_grid_quotes_are_one_offset_outside_fundamental() -> None:
    buy = PassiveLiquidityPolicy(Side.BUY, Decimal("10"), Decimal("1"))
    sell = PassiveLiquidityPolicy(Side.SELL, Decimal("10"), Decimal("1"))

    bid = buy.decide(_obs(), agent_id="lp-bid")
    ask = sell.decide(_obs(), agent_id="lp-ask")

    assert bid.side is Side.BUY
    assert bid.price == Decimal("99")
    assert ask.side is Side.SELL
    assert ask.price == Decimal("101")
    assert bid.time_in_force is TimeInForce.GOOD_TIL_CANCELLED
    assert ask.time_in_force is TimeInForce.GOOD_TIL_CANCELLED


def test_non_grid_reference_quotes_outward_from_nearest_grid() -> None:
    buy = PassiveLiquidityPolicy(Side.BUY, Decimal("1"), Decimal("1"))
    sell = PassiveLiquidityPolicy(Side.SELL, Decimal("1"), Decimal("1"))

    assert buy.decide(_obs(fundamental="100.25"), agent_id="b").price == Decimal("99")
    assert sell.decide(_obs(fundamental="100.25"), agent_id="s").price == Decimal("102")


def test_policy_holds_outside_configured_quote_step() -> None:
    policy = PassiveLiquidityPolicy(
        Side.BUY,
        Decimal("1"),
        Decimal("0.01"),
        quote_step=2,
    )

    assert policy.decide(_obs(step=1), agent_id="b").is_hold
    assert not policy.decide(_obs(step=2), agent_id="b").is_hold
    assert policy.decide(_obs(step=3), agent_id="b").is_hold


@pytest.mark.parametrize(
    "kwargs",
    [
        {"side": "buy", "quantity": Decimal("1"), "tick_size": Decimal("1")},
        {"side": Side.BUY, "quantity": Decimal("0"), "tick_size": Decimal("1")},
        {"side": Side.BUY, "quantity": Decimal("1"), "tick_size": Decimal("0")},
        {
            "side": Side.BUY,
            "quantity": Decimal("1"),
            "tick_size": Decimal("1"),
            "offset_ticks": 0,
        },
        {
            "side": Side.BUY,
            "quantity": Decimal("1"),
            "tick_size": Decimal("1"),
            "offset_ticks": True,
        },
        {
            "side": Side.BUY,
            "quantity": Decimal("1"),
            "tick_size": Decimal("1"),
            "quote_step": -1,
        },
        {
            "side": Side.BUY,
            "quantity": Decimal("1"),
            "tick_size": Decimal("1"),
            "quote_step": True,
        },
    ],
)
def test_invalid_configuration_is_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(InvalidPolicyError):
        PassiveLiquidityPolicy(**kwargs)  # type: ignore[arg-type]


def test_invalid_policy_inputs_are_rejected() -> None:
    policy = PassiveLiquidityPolicy(Side.BUY, Decimal("1"), Decimal("1"))

    with pytest.raises(InvalidPolicyError, match="MarketObservation"):
        policy.decide(object(), agent_id="b")  # type: ignore[arg-type]

    with pytest.raises(InvalidPolicyError, match="agent_id"):
        policy.decide(_obs(), agent_id="")

    too_wide = PassiveLiquidityPolicy(
        Side.BUY,
        Decimal("1"),
        Decimal("10"),
        offset_ticks=1,
    )
    with pytest.raises(InvalidPolicyError, match="non-positive"):
        too_wide.decide(_obs(fundamental="5"), agent_id="b")
