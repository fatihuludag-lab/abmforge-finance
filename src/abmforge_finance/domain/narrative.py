"""Immutable narrative-state, exposure, and signal primitives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from itertools import pairwise

from abmforge_finance.domain._validation import (
    require_decimal,
    require_non_empty_text,
    require_non_negative_int,
)
from abmforge_finance.exceptions import InvalidNarrativeError

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _unit_interval_decimal(value: object, *, field_name: str) -> Decimal:
    converted = require_decimal(
        value,
        field_name=field_name,
        error_type=InvalidNarrativeError,
        minimum=_ZERO,
    )
    if converted > _ONE:
        raise InvalidNarrativeError(f"{field_name} must be <= 1")
    return converted


class NarrativeDirection(str, Enum):
    """Signed direction of one narrative state."""

    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"

    @property
    def sign(self) -> Decimal:
        """Return the exact directional sign in {-1, 0, +1}."""

        if self is NarrativeDirection.BEARISH:
            return Decimal("-1")
        if self is NarrativeDirection.BULLISH:
            return _ONE
        return _ZERO


@dataclass(frozen=True, slots=True)
class NarrativeState:
    """One frozen narrative regime on a half-open discrete-time interval.

    ``active_from`` is inclusive and ``active_until`` is exclusive. Repeated
    ``narrative_id`` values can therefore represent a time-varying narrative stream
    when their intervals do not overlap.
    """

    narrative_id: str
    direction: NarrativeDirection
    strength: Decimal
    confidence: Decimal
    active_from: int
    active_until: int

    def __post_init__(self) -> None:
        require_non_empty_text(
            self.narrative_id,
            field_name="narrative_id",
            error_type=InvalidNarrativeError,
        )
        if not isinstance(self.direction, NarrativeDirection):
            raise InvalidNarrativeError("direction must be a NarrativeDirection")
        _unit_interval_decimal(self.strength, field_name="strength")
        _unit_interval_decimal(self.confidence, field_name="confidence")
        start = require_non_negative_int(
            self.active_from,
            field_name="active_from",
            error_type=InvalidNarrativeError,
        )
        end = require_non_negative_int(
            self.active_until,
            field_name="active_until",
            error_type=InvalidNarrativeError,
        )
        if end <= start:
            raise InvalidNarrativeError("active_until must be greater than active_from")

    def is_active(self, step: int) -> bool:
        """Return whether this state is active at one discrete market step."""

        validated = require_non_negative_int(
            step,
            field_name="step",
            error_type=InvalidNarrativeError,
        )
        return self.active_from <= validated < self.active_until

    @property
    def signed_strength(self) -> Decimal:
        """Return direction * strength * confidence exactly."""

        return self.direction.sign * self.strength * self.confidence


@dataclass(frozen=True, slots=True)
class NarrativeExposure:
    """Agent-specific exposure to one conceptual narrative stream."""

    agent_id: str
    narrative_id: str
    exposure_weight: Decimal

    def __post_init__(self) -> None:
        require_non_empty_text(
            self.agent_id,
            field_name="agent_id",
            error_type=InvalidNarrativeError,
        )
        require_non_empty_text(
            self.narrative_id,
            field_name="narrative_id",
            error_type=InvalidNarrativeError,
        )
        _unit_interval_decimal(self.exposure_weight, field_name="exposure_weight")


@dataclass(frozen=True, slots=True)
class NarrativeSignal:
    """Exact aggregate narrative pressure for one agent and one market step."""

    agent_id: str
    step: int
    value: Decimal
    contributing_narrative_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty_text(
            self.agent_id,
            field_name="agent_id",
            error_type=InvalidNarrativeError,
        )
        require_non_negative_int(
            self.step,
            field_name="step",
            error_type=InvalidNarrativeError,
        )
        require_decimal(
            self.value,
            field_name="value",
            error_type=InvalidNarrativeError,
        )
        if not isinstance(self.contributing_narrative_ids, tuple):
            raise InvalidNarrativeError("contributing_narrative_ids must be a tuple")
        for narrative_id in self.contributing_narrative_ids:
            require_non_empty_text(
                narrative_id,
                field_name="contributing_narrative_id",
                error_type=InvalidNarrativeError,
            )
        if len(set(self.contributing_narrative_ids)) != len(self.contributing_narrative_ids):
            raise InvalidNarrativeError("contributing_narrative_ids must be unique")


def _validate_narrative_configuration(
    narratives: tuple[NarrativeState, ...],
    exposures: tuple[NarrativeExposure, ...],
) -> None:
    if not isinstance(narratives, tuple) or not all(
        isinstance(state, NarrativeState) for state in narratives
    ):
        raise InvalidNarrativeError("narratives must be a tuple of NarrativeState values")
    if not isinstance(exposures, tuple) or not all(
        isinstance(exposure, NarrativeExposure) for exposure in exposures
    ):
        raise InvalidNarrativeError("exposures must be a tuple of NarrativeExposure values")

    by_narrative: dict[str, list[NarrativeState]] = {}
    for state in narratives:
        by_narrative.setdefault(state.narrative_id, []).append(state)

    for narrative_id, states in by_narrative.items():
        ordered = sorted(
            states,
            key=lambda item: (item.active_from, item.active_until),
        )
        for previous, current in pairwise(ordered):
            if current.active_from < previous.active_until:
                raise InvalidNarrativeError(
                    f"narrative_id {narrative_id!r} has overlapping active intervals"
                )

    exposure_keys = tuple((exposure.agent_id, exposure.narrative_id) for exposure in exposures)
    if len(set(exposure_keys)) != len(exposure_keys):
        raise InvalidNarrativeError("agent_id/narrative_id exposure pairs must be unique")

    known_ids = set(by_narrative)
    unknown_ids = sorted(
        {exposure.narrative_id for exposure in exposures if exposure.narrative_id not in known_ids}
    )
    if unknown_ids:
        raise InvalidNarrativeError(
            "exposures reference unknown narrative_id values: "
            + ", ".join(repr(value) for value in unknown_ids)
        )


def _aggregate_narrative_signal_validated(
    narratives: tuple[NarrativeState, ...],
    exposures: tuple[NarrativeExposure, ...],
    *,
    agent_id: str,
    step: int,
) -> NarrativeSignal:
    exposure_by_id = {
        exposure.narrative_id: exposure.exposure_weight
        for exposure in exposures
        if exposure.agent_id == agent_id
    }

    total = _ZERO
    contributing: set[str] = set()
    for state in narratives:
        if not state.is_active(step):
            continue
        weight = exposure_by_id.get(state.narrative_id)
        if weight is None:
            continue
        contribution = state.signed_strength * weight
        total += contribution
        if contribution != _ZERO:
            contributing.add(state.narrative_id)

    return NarrativeSignal(
        agent_id=agent_id,
        step=step,
        value=total,
        contributing_narrative_ids=tuple(sorted(contributing)),
    )


def aggregate_narrative_signal(
    narratives: tuple[NarrativeState, ...],
    exposures: tuple[NarrativeExposure, ...],
    *,
    agent_id: str,
    step: int,
) -> NarrativeSignal:
    """Aggregate active narrative pressure with exact Decimal arithmetic.

    For each active narrative state the contribution is

    ``direction * strength * confidence * exposure_weight``.

    Contributions from simultaneously active distinct narrative streams add
    algebraically. Configuration order cannot change the numeric signal.
    """

    validated_agent = require_non_empty_text(
        agent_id,
        field_name="agent_id",
        error_type=InvalidNarrativeError,
    )
    validated_step = require_non_negative_int(
        step,
        field_name="step",
        error_type=InvalidNarrativeError,
    )
    _validate_narrative_configuration(narratives, exposures)
    return _aggregate_narrative_signal_validated(
        narratives,
        exposures,
        agent_id=validated_agent,
        step=validated_step,
    )
