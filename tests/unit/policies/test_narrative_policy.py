"""Tests for the deterministic narrative trading policy."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    InvalidPolicyError,
    MarketObservation,
    NarrativeDirection,
    NarrativeExposure,
    NarrativePolicy,
    NarrativeState,
    Side,
    Trader,
)


def _observation(step: int = 0) -> MarketObservation:
    return MarketObservation(
        step=step,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
        mid_price=Decimal("100"),
    )


def _policy(
    direction: NarrativeDirection,
    *,
    exposure_weight: Decimal = Decimal("1"),
    strength: Decimal = Decimal("1"),
    confidence: Decimal = Decimal("1"),
    threshold: Decimal = Decimal("0"),
) -> NarrativePolicy:
    return NarrativePolicy(
        quantity=Decimal("2"),
        narratives=(
            NarrativeState(
                "n",
                direction,
                strength,
                confidence,
                0,
                2,
            ),
        ),
        exposures=(NarrativeExposure("agent", "n", exposure_weight),),
        decision_threshold=threshold,
    )


def test_policy_buys_bullish_sells_bearish_and_holds_neutral() -> None:
    assert (
        _policy(NarrativeDirection.BULLISH).decide(_observation(), agent_id="agent").side
        is Side.BUY
    )
    assert (
        _policy(NarrativeDirection.BEARISH).decide(_observation(), agent_id="agent").side
        is Side.SELL
    )
    assert (
        _policy(NarrativeDirection.NEUTRAL)
        .decide(
            _observation(),
            agent_id="agent",
        )
        .is_hold
    )


def test_policy_uses_strict_symmetric_dead_band() -> None:
    policy = _policy(
        NarrativeDirection.BULLISH,
        strength=Decimal("0.5"),
        threshold=Decimal("0.5"),
    )
    assert policy.signal(_observation(), agent_id="agent").value == Decimal("0.5")
    assert policy.decide(_observation(), agent_id="agent").is_hold

    active = _policy(
        NarrativeDirection.BULLISH,
        strength=Decimal("0.6"),
        threshold=Decimal("0.5"),
    )
    assert active.decide(_observation(), agent_id="agent").side is Side.BUY


def test_same_policy_can_generate_agent_specific_decisions_from_exposure() -> None:
    policy = NarrativePolicy(
        Decimal("1"),
        narratives=(
            NarrativeState(
                "n",
                NarrativeDirection.BULLISH,
                Decimal("1"),
                Decimal("1"),
                0,
                1,
            ),
        ),
        exposures=(
            NarrativeExposure("high", "n", Decimal("1")),
            NarrativeExposure("low", "n", Decimal("0.1")),
        ),
        decision_threshold=Decimal("0.5"),
    )

    assert policy.decide(_observation(), agent_id="high").side is Side.BUY
    assert policy.decide(_observation(), agent_id="low").is_hold
    assert policy.decide(_observation(), agent_id="none").is_hold


def test_policy_follows_time_varying_narrative_stream() -> None:
    policy = NarrativePolicy(
        Decimal("1"),
        narratives=(
            NarrativeState(
                "macro",
                NarrativeDirection.BULLISH,
                Decimal("1"),
                Decimal("1"),
                0,
                1,
            ),
            NarrativeState(
                "macro",
                NarrativeDirection.BEARISH,
                Decimal("1"),
                Decimal("1"),
                1,
                2,
            ),
        ),
        exposures=(NarrativeExposure("agent", "macro", Decimal("1")),),
    )

    assert policy.decide(_observation(0), agent_id="agent").side is Side.BUY
    assert policy.decide(_observation(1), agent_id="agent").side is Side.SELL
    assert policy.decide(_observation(2), agent_id="agent").is_hold


def test_policy_repeated_calls_are_exactly_deterministic() -> None:
    policy = _policy(
        NarrativeDirection.BULLISH,
        exposure_weight=Decimal("0.7"),
        confidence=Decimal("0.8"),
    )
    first = policy.signal(_observation(), agent_id="agent")
    second = policy.signal(_observation(), agent_id="agent")
    assert first == second
    assert policy.decide(_observation(), agent_id="agent") == policy.decide(
        _observation(),
        agent_id="agent",
    )


@pytest.mark.parametrize(
    "quantity",
    [Decimal("0"), Decimal("-1")],
)
def test_policy_rejects_non_positive_quantity(quantity: Decimal) -> None:
    with pytest.raises(InvalidPolicyError):
        NarrativePolicy(quantity, (), ())


def test_policy_rejects_negative_threshold_and_invalid_narrative_configuration() -> None:
    with pytest.raises(InvalidPolicyError):
        NarrativePolicy(
            Decimal("1"),
            (),
            (),
            decision_threshold=Decimal("-0.1"),
        )

    with pytest.raises(InvalidPolicyError, match="narrative configuration"):
        NarrativePolicy(
            Decimal("1"),
            (),
            (NarrativeExposure("agent", "missing", Decimal("1")),),
        )


def test_policy_rejects_invalid_runtime_inputs() -> None:
    policy = _policy(NarrativeDirection.BULLISH)

    with pytest.raises(InvalidPolicyError, match="MarketObservation"):
        policy.decide(object(), agent_id="agent")  # type: ignore[arg-type]

    with pytest.raises(InvalidPolicyError, match="agent_id"):
        policy.decide(_observation(), agent_id="")


def test_narrative_policy_composes_with_existing_trader_contract() -> None:
    trader = Trader("agent", _policy(NarrativeDirection.BULLISH))

    decision = trader.decide(_observation())
    plan = trader.plan(_observation())

    assert decision.side is Side.BUY
    assert plan.cancellations == ()
    assert plan.decision == decision
