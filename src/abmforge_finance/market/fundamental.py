"""Deterministic and explicitly seeded fundamental-value processes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from abmforge_finance.exceptions import (
    FundamentalPathExhaustedError,
    InvalidFundamentalValueError,
    InvalidMarketTimeError,
)

_ZERO = Decimal("0")
_MASK_64 = (1 << 64) - 1
_SPLITMIX_INCREMENT = 0x9E3779B97F4A7C15
_SPLITMIX_MUL_1 = 0xBF58476D1CE4E5B9
_SPLITMIX_MUL_2 = 0x94D049BB133111EB


def _validate_step(value: object, *, field_name: str = "step") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidMarketTimeError(f"{field_name} must be an integer")
    if value < 0:
        raise InvalidMarketTimeError(f"{field_name} must be non-negative")
    return value


def _validate_positive_decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise InvalidFundamentalValueError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise InvalidFundamentalValueError(f"{field_name} must be finite")
    if value <= _ZERO:
        raise InvalidFundamentalValueError(f"{field_name} must be positive")
    return value


def _validate_int(value: object, *, field_name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidFundamentalValueError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise InvalidFundamentalValueError(f"{field_name} must be >= {minimum}")
    return value


class FundamentalValueProcess(Protocol):
    """Structural protocol for a time-indexed positive fundamental value."""

    def value_at(self, step: int) -> Decimal:
        """Return the fundamental value at one non-negative integer period."""
        ...


@dataclass(frozen=True, slots=True)
class ConstantFundamentalValue:
    """Return one exact positive ``Decimal`` value at every valid period."""

    value: Decimal

    def __post_init__(self) -> None:
        _validate_positive_decimal(self.value, field_name="value")

    def value_at(self, step: int) -> Decimal:
        """Return the constant value after validating the requested period."""
        _validate_step(step)
        return self.value


@dataclass(frozen=True, slots=True)
class DeterministicFundamentalPath:
    """Expose a finite frozen sequence of exact positive fundamental values.

    ``values[0]`` corresponds to ``start_step``. Requests outside the frozen horizon
    fail explicitly rather than silently extending or carrying the final value.
    """

    values: tuple[Decimal, ...]
    start_step: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple) or not self.values:
            raise InvalidFundamentalValueError("values must be a non-empty tuple")
        _validate_step(self.start_step, field_name="start_step")
        for index, value in enumerate(self.values):
            _validate_positive_decimal(value, field_name=f"values[{index}]")

    @property
    def end_step(self) -> int:
        """Return the inclusive final period available in the frozen path."""
        return self.start_step + len(self.values) - 1

    def value_at(self, step: int) -> Decimal:
        """Return the exact frozen value for ``step`` or fail outside the horizon."""
        validated = _validate_step(step)
        index = validated - self.start_step
        if index < 0 or index >= len(self.values):
            raise FundamentalPathExhaustedError(
                f"step {validated} is outside frozen path [{self.start_step}, {self.end_step}]"
            )
        return self.values[index]


class _SplitMix64:
    """Minimal package-owned SplitMix64 stream with fixed integer semantics."""

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK_64

    def next_u64(self) -> int:
        """Return the next deterministic unsigned 64-bit integer."""
        self._state = (self._state + _SPLITMIX_INCREMENT) & _MASK_64
        value = self._state
        value = ((value ^ (value >> 30)) * _SPLITMIX_MUL_1) & _MASK_64
        value = ((value ^ (value >> 27)) * _SPLITMIX_MUL_2) & _MASK_64
        return (value ^ (value >> 31)) & _MASK_64

    def bounded(self, bound: int) -> int:
        """Return an unbiased deterministic integer in ``range(bound)``."""
        limit = (1 << 64) - ((1 << 64) % bound)
        while True:
            value = self.next_u64()
            if value < limit:
                return value % bound


class SeededFundamentalRandomWalk:
    """Generate a reproducible additive synthetic fundamental-value path.

    Each transition adds ``step_size * (drift_units + shock_units)``. Shock units are
    sampled uniformly from the inclusive integer interval
    ``[-max_abs_shock_units, max_abs_shock_units]`` using a package-owned SplitMix64
    stream. Values are floored at ``minimum_value`` to preserve positivity.

    This process is a controlled synthetic baseline, not an empirical claim about how
    fundamentals evolve. The explicit integer-shock mechanism is chosen so the same
    parameters and seed produce the same exact ``Decimal`` path without depending on
    Python's or NumPy's global RNG state.
    """

    __slots__ = (
        "_drift_units",
        "_initial_value",
        "_max_abs_shock_units",
        "_minimum_value",
        "_rng",
        "_seed",
        "_step_size",
        "_values",
    )

    def __init__(
        self,
        initial_value: Decimal,
        *,
        seed: int,
        step_size: Decimal,
        max_abs_shock_units: int,
        drift_units: int = 0,
        minimum_value: Decimal | None = None,
    ) -> None:
        initial = _validate_positive_decimal(initial_value, field_name="initial_value")
        validated_seed = _validate_int(seed, field_name="seed", minimum=0)
        if validated_seed > _MASK_64:
            raise InvalidFundamentalValueError(f"seed must be <= {_MASK_64}")
        increment = _validate_positive_decimal(step_size, field_name="step_size")
        max_shock = _validate_int(
            max_abs_shock_units,
            field_name="max_abs_shock_units",
            minimum=0,
        )
        if (2 * max_shock) + 1 > 1 << 64:
            raise InvalidFundamentalValueError("shock span must fit within 64 bits")
        drift = _validate_int(drift_units, field_name="drift_units")
        floor = (
            increment
            if minimum_value is None
            else _validate_positive_decimal(
                minimum_value,
                field_name="minimum_value",
            )
        )
        if initial < floor:
            raise InvalidFundamentalValueError("initial_value must be >= minimum_value")

        self._initial_value = initial
        self._seed = validated_seed
        self._step_size = increment
        self._max_abs_shock_units = max_shock
        self._drift_units = drift
        self._minimum_value = floor
        self._rng = _SplitMix64(validated_seed)
        self._values: list[Decimal] = [initial]

    @property
    def initial_value(self) -> Decimal:
        """Return the exact initial value at period zero."""
        return self._initial_value

    @property
    def seed(self) -> int:
        """Return the explicit 64-bit seed."""
        return self._seed

    @property
    def step_size(self) -> Decimal:
        """Return the exact value increment represented by one shock unit."""
        return self._step_size

    @property
    def max_abs_shock_units(self) -> int:
        """Return the symmetric maximum stochastic shock magnitude in units."""
        return self._max_abs_shock_units

    @property
    def drift_units(self) -> int:
        """Return the deterministic additive drift in units per transition."""
        return self._drift_units

    @property
    def minimum_value(self) -> Decimal:
        """Return the positive floor applied after every transition."""
        return self._minimum_value

    def value_at(self, step: int) -> Decimal:
        """Return the exact seeded value for a period, extending the cached path if needed."""
        validated = _validate_step(step)
        while len(self._values) <= validated:
            span = (2 * self._max_abs_shock_units) + 1
            shock_units = self._rng.bounded(span) - self._max_abs_shock_units
            total_units = self._drift_units + shock_units
            candidate = self._values[-1] + (self._step_size * total_units)
            self._values.append(max(candidate, self._minimum_value))
        return self._values[validated]
