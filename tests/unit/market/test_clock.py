"""Unit tests for deterministic discrete market time."""

import pytest

from abmforge_finance import InvalidMarketTimeError, MarketClock


def test_clock_starts_at_requested_non_negative_step() -> None:
    clock = MarketClock(7)
    assert clock.start_step == 7
    assert clock.current_step == 7


def test_clock_advances_only_from_explicit_integer_steps() -> None:
    clock = MarketClock()
    assert clock.advance() == 1
    assert clock.advance(4) == 5
    assert clock.current_step == 5


@pytest.mark.parametrize("value", [-1, True, 1.5, "1"])
def test_invalid_start_step_is_rejected(value: object) -> None:
    with pytest.raises(InvalidMarketTimeError):
        MarketClock(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1"])
def test_invalid_advance_is_rejected_without_mutation(value: object) -> None:
    clock = MarketClock(3)
    with pytest.raises(InvalidMarketTimeError):
        clock.advance(value)  # type: ignore[arg-type]
    assert clock.current_step == 3
