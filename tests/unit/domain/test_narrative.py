"""Tests for immutable narrative state, exposure, and signal values."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    InvalidNarrativeError,
    NarrativeDirection,
    NarrativeExposure,
    NarrativeSignal,
    NarrativeState,
    aggregate_narrative_signal,
)


def test_narrative_direction_has_exact_signed_values() -> None:
    assert NarrativeDirection.BEARISH.sign == Decimal("-1")
    assert NarrativeDirection.NEUTRAL.sign == Decimal("0")
    assert NarrativeDirection.BULLISH.sign == Decimal("1")


def test_state_uses_half_open_activity_window_and_exact_signed_strength() -> None:
    state = NarrativeState(
        "growth",
        NarrativeDirection.BULLISH,
        Decimal("0.8"),
        Decimal("0.5"),
        2,
        5,
    )

    assert not state.is_active(1)
    assert state.is_active(2)
    assert state.is_active(4)
    assert not state.is_active(5)
    assert state.signed_strength == Decimal("0.40")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"narrative_id": ""},
        {"direction": "bullish"},
        {"strength": Decimal("-0.1")},
        {"strength": Decimal("1.1")},
        {"confidence": Decimal("-0.1")},
        {"confidence": Decimal("1.1")},
        {"active_from": -1},
        {"active_from": 2, "active_until": 2},
    ],
)
def test_state_rejects_invalid_domain_values(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "narrative_id": "n",
        "direction": NarrativeDirection.BULLISH,
        "strength": Decimal("1"),
        "confidence": Decimal("1"),
        "active_from": 0,
        "active_until": 2,
    }
    values.update(kwargs)

    with pytest.raises(InvalidNarrativeError):
        NarrativeState(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"agent_id": ""},
        {"narrative_id": ""},
        {"exposure_weight": Decimal("-0.1")},
        {"exposure_weight": Decimal("1.1")},
    ],
)
def test_exposure_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "agent_id": "agent",
        "narrative_id": "n",
        "exposure_weight": Decimal("1"),
    }
    values.update(kwargs)

    with pytest.raises(InvalidNarrativeError):
        NarrativeExposure(**values)  # type: ignore[arg-type]


def test_signal_aggregates_multiple_active_narratives_exactly() -> None:
    narratives = (
        NarrativeState(
            "bull",
            NarrativeDirection.BULLISH,
            Decimal("1"),
            Decimal("0.8"),
            0,
            2,
        ),
        NarrativeState(
            "bear",
            NarrativeDirection.BEARISH,
            Decimal("0.5"),
            Decimal("1"),
            0,
            2,
        ),
    )
    exposures = (
        NarrativeExposure("agent", "bull", Decimal("0.75")),
        NarrativeExposure("agent", "bear", Decimal("0.50")),
    )

    signal = aggregate_narrative_signal(
        narratives,
        exposures,
        agent_id="agent",
        step=0,
    )

    assert signal.value == Decimal("0.35")
    assert signal.contributing_narrative_ids == ("bear", "bull")


def test_signal_is_agent_specific_and_zero_without_exposure() -> None:
    state = NarrativeState(
        "n",
        NarrativeDirection.BULLISH,
        Decimal("1"),
        Decimal("1"),
        0,
        1,
    )
    exposures = (NarrativeExposure("a", "n", Decimal("0.25")),)

    assert aggregate_narrative_signal(
        (state,),
        exposures,
        agent_id="a",
        step=0,
    ).value == Decimal("0.25")
    assert aggregate_narrative_signal(
        (state,),
        exposures,
        agent_id="b",
        step=0,
    ) == NarrativeSignal("b", 0, Decimal("0"), ())


def test_one_narrative_stream_can_change_state_across_non_overlapping_windows() -> None:
    states = (
        NarrativeState(
            "macro",
            NarrativeDirection.BULLISH,
            Decimal("1"),
            Decimal("1"),
            0,
            2,
        ),
        NarrativeState(
            "macro",
            NarrativeDirection.BEARISH,
            Decimal("1"),
            Decimal("1"),
            2,
            4,
        ),
    )
    exposures = (NarrativeExposure("a", "macro", Decimal("1")),)

    assert aggregate_narrative_signal(
        states,
        exposures,
        agent_id="a",
        step=1,
    ).value == Decimal("1")
    assert aggregate_narrative_signal(
        states,
        exposures,
        agent_id="a",
        step=2,
    ).value == Decimal("-1")


def test_signal_rejects_ambiguous_or_broken_configuration() -> None:
    overlapping = (
        NarrativeState(
            "n",
            NarrativeDirection.BULLISH,
            Decimal("1"),
            Decimal("1"),
            0,
            3,
        ),
        NarrativeState(
            "n",
            NarrativeDirection.BEARISH,
            Decimal("1"),
            Decimal("1"),
            2,
            4,
        ),
    )
    with pytest.raises(InvalidNarrativeError, match="overlapping"):
        aggregate_narrative_signal(
            overlapping,
            (NarrativeExposure("a", "n", Decimal("1")),),
            agent_id="a",
            step=2,
        )

    state = NarrativeState(
        "n",
        NarrativeDirection.BULLISH,
        Decimal("1"),
        Decimal("1"),
        0,
        1,
    )
    duplicate = (
        NarrativeExposure("a", "n", Decimal("0.5")),
        NarrativeExposure("a", "n", Decimal("0.6")),
    )
    with pytest.raises(InvalidNarrativeError, match="unique"):
        aggregate_narrative_signal(
            (state,),
            duplicate,
            agent_id="a",
            step=0,
        )

    with pytest.raises(InvalidNarrativeError, match="unknown"):
        aggregate_narrative_signal(
            (state,),
            (NarrativeExposure("a", "other", Decimal("1")),),
            agent_id="a",
            step=0,
        )


def test_signal_is_configuration_order_independent() -> None:
    states = (
        NarrativeState(
            "a",
            NarrativeDirection.BULLISH,
            Decimal("0.8"),
            Decimal("1"),
            0,
            1,
        ),
        NarrativeState(
            "b",
            NarrativeDirection.BEARISH,
            Decimal("0.2"),
            Decimal("1"),
            0,
            1,
        ),
    )
    exposures = (
        NarrativeExposure("agent", "a", Decimal("1")),
        NarrativeExposure("agent", "b", Decimal("1")),
    )

    left = aggregate_narrative_signal(states, exposures, agent_id="agent", step=0)
    right = aggregate_narrative_signal(
        tuple(reversed(states)),
        tuple(reversed(exposures)),
        agent_id="agent",
        step=0,
    )
    assert left == right
