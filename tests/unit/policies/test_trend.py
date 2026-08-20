"""Unit tests for the directional trend-following baseline policy."""

from decimal import Decimal

from abmforge_finance import MarketObservation, Side, TrendFollowingPolicy


def obs(change: Decimal | None) -> MarketObservation:
    return MarketObservation(
        step=4,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
        price_change=change,
    )


def test_trend_policy_follows_signed_change() -> None:
    policy = TrendFollowingPolicy(Decimal("1"), minimum_change=Decimal("0.25"))
    assert policy.decide(obs(Decimal("0.50")), agent_id="a").side is Side.BUY
    assert policy.decide(obs(Decimal("-0.50")), agent_id="a").side is Side.SELL


def test_trend_policy_holds_inside_dead_band_and_without_signal() -> None:
    policy = TrendFollowingPolicy(Decimal("1"), minimum_change=Decimal("0.25"))
    assert policy.decide(obs(Decimal("0.10")), agent_id="a").is_hold
    assert policy.decide(obs(None), agent_id="a").is_hold
