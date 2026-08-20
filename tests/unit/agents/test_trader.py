"""Unit tests for policy-composed trader identities."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    FundamentalPolicy,
    InvalidPolicyError,
    InvalidTraderError,
    MarketObservation,
    NoisePolicy,
    Trader,
)


def obs() -> MarketObservation:
    return MarketObservation(
        step=1,
        instrument_id="ACME",
        fundamental_value=Decimal("101"),
        mid_price=Decimal("100"),
    )


def test_trader_delegates_without_owning_market_state() -> None:
    trader = Trader("agent-1", FundamentalPolicy(Decimal("1")))
    before = obs()
    decision = trader.decide(before)
    assert not decision.is_hold
    assert before == obs()
    assert set(trader.__slots__) == {"agent_id", "policy"}


def test_trader_can_replace_policy_without_changing_identity() -> None:
    trader = Trader("agent-1", FundamentalPolicy(Decimal("1")))
    replacement = trader.with_policy(NoisePolicy(Decimal("1"), seed=7))
    assert replacement.agent_id == trader.agent_id
    assert replacement.policy is not trader.policy


def test_trader_rejects_invalid_identity_and_policy() -> None:
    with pytest.raises(InvalidTraderError):
        Trader("", FundamentalPolicy(Decimal("1")))
    with pytest.raises(InvalidTraderError):
        Trader("a", object())  # type: ignore[arg-type]


def test_trader_rejects_non_decision_policy_output() -> None:
    class BadPolicy:
        def decide(self, observation: MarketObservation, *, agent_id: str) -> object:
            return object()

    trader = Trader("a", BadPolicy())  # type: ignore[arg-type]
    with pytest.raises(InvalidPolicyError):
        trader.decide(obs())
