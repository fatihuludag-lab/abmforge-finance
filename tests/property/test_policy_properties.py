"""Property tests for baseline policy determinism and decision validity."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import MarketObservation, NoisePolicy


@given(
    seed=st.integers(min_value=0, max_value=(1 << 64) - 1),
    step=st.integers(min_value=0, max_value=1_000_000),
    activity_bps=st.integers(min_value=0, max_value=10_000),
)
def test_noise_policy_replays_exactly(seed: int, step: int, activity_bps: int) -> None:
    observation = MarketObservation(
        step=step,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
    )
    policy = NoisePolicy(Decimal("1"), seed=seed, activity_bps=activity_bps)
    assert policy.decide(observation, agent_id="agent") == policy.decide(
        observation, agent_id="agent"
    )


@given(step=st.integers(min_value=0, max_value=1_000_000))
def test_noise_decisions_remain_valid_market_or_hold_decisions(step: int) -> None:
    observation = MarketObservation(
        step=step,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
    )
    decision = NoisePolicy(Decimal("2"), seed=20260821).decide(
        observation,
        agent_id="agent",
    )
    assert decision.is_hold or decision.quantity == Decimal("2")
