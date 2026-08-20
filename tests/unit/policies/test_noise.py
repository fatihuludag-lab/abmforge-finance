"""Unit tests for the explicitly seeded stateless noise policy."""

from decimal import Decimal

import pytest

from abmforge_finance import InvalidPolicyError, MarketObservation, NoisePolicy


def obs(step: int) -> MarketObservation:
    return MarketObservation(
        step=step,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
    )


def test_noise_policy_exact_replay_is_stateless() -> None:
    policy = NoisePolicy(Decimal("1"), seed=42, activity_bps=10_000)
    first = policy.decide(obs(7), agent_id="agent-1")
    policy.decide(obs(100), agent_id="agent-1")
    second = policy.decide(obs(7), agent_id="agent-1")
    assert first == second
    assert not first.is_hold


def test_noise_activity_extremes_are_exact() -> None:
    assert NoisePolicy(Decimal("1"), seed=1, activity_bps=0).decide(obs(0), agent_id="a").is_hold
    assert (
        not NoisePolicy(Decimal("1"), seed=1, activity_bps=10_000)
        .decide(obs(0), agent_id="a")
        .is_hold
    )


@pytest.mark.parametrize("seed", [-1, 1 << 64, True])
def test_noise_policy_rejects_invalid_seed(seed: object) -> None:
    with pytest.raises(InvalidPolicyError):
        NoisePolicy(Decimal("1"), seed=seed)  # type: ignore[arg-type]
