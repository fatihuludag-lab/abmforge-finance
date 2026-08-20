"""Property tests for market-time and fundamental-value reproducibility."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import MarketClock, SeededFundamentalRandomWalk


@given(
    start=st.integers(min_value=0, max_value=1_000_000),
    increments=st.lists(st.integers(min_value=1, max_value=10_000), min_size=0, max_size=50),
)
def test_market_clock_is_exactly_monotone(start: int, increments: list[int]) -> None:
    clock = MarketClock(start)
    expected = start
    for increment in increments:
        expected += increment
        assert clock.advance(increment) == expected
    assert clock.current_step == expected


@given(
    seed=st.integers(min_value=0, max_value=(1 << 64) - 1),
    max_shock=st.integers(min_value=0, max_value=25),
    step=st.integers(min_value=0, max_value=100),
)
def test_seeded_fundamental_replay_is_exact(seed: int, max_shock: int, step: int) -> None:
    first = SeededFundamentalRandomWalk(
        Decimal("100"),
        seed=seed,
        step_size=Decimal("0.01"),
        max_abs_shock_units=max_shock,
        drift_units=1,
        minimum_value=Decimal("0.01"),
    )
    second = SeededFundamentalRandomWalk(
        Decimal("100"),
        seed=seed,
        step_size=Decimal("0.01"),
        max_abs_shock_units=max_shock,
        drift_units=1,
        minimum_value=Decimal("0.01"),
    )
    assert first.value_at(step) == second.value_at(step)
    assert first.value_at(step // 2) == second.value_at(step // 2)


@given(
    seed=st.integers(min_value=0, max_value=(1 << 64) - 1),
    step=st.integers(min_value=0, max_value=200),
)
def test_seeded_fundamental_stays_at_or_above_explicit_floor(seed: int, step: int) -> None:
    process = SeededFundamentalRandomWalk(
        Decimal("1"),
        seed=seed,
        step_size=Decimal("0.25"),
        max_abs_shock_units=10,
        drift_units=-1,
        minimum_value=Decimal("0.25"),
    )
    assert process.value_at(step) >= Decimal("0.25")
