"""Deterministic discrete market time."""

from __future__ import annotations

from abmforge_finance.exceptions import InvalidMarketTimeError


def _validate_step(value: object, *, field_name: str, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidMarketTimeError(f"{field_name} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        comparator = "non-negative" if allow_zero else "positive"
        raise InvalidMarketTimeError(f"{field_name} must be {comparator}")
    return value


class MarketClock:
    """Own deterministic integer-valued economic simulation time.

    The clock intentionally has no wall-clock, timezone, or framework dependency.
    ``current_step`` starts at ``start_step`` and only moves forward through explicit
    calls to :meth:`advance`.

    Parameters
    ----------
    start_step
        Initial non-negative integer period.

    Determinism
    -----------
    Time advances only from explicit integer inputs; no system clock is read.
    """

    __slots__ = ("_current_step", "_start_step")

    def __init__(self, start_step: int = 0) -> None:
        validated = _validate_step(start_step, field_name="start_step")
        self._start_step = validated
        self._current_step = validated

    @property
    def start_step(self) -> int:
        """Return the immutable initial period."""
        return self._start_step

    @property
    def current_step(self) -> int:
        """Return the current deterministic market period."""
        return self._current_step

    def advance(self, steps: int = 1) -> int:
        """Move forward by a positive integer number of periods and return the result."""
        increment = _validate_step(steps, field_name="steps", allow_zero=False)
        self._current_step += increment
        return self._current_step
