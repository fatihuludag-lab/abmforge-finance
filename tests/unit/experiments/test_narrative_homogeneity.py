"""Unit tests for deterministic population narrative-homogeneity treatments."""

from decimal import Decimal
from itertools import pairwise

import pytest

from abmforge_finance import NarrativeDirection, Side
from abmforge_finance.exceptions import InvalidNarrativeTreatmentError
from abmforge_finance.experiments import (
    NarrativeAgentAssignment,
    NarrativeHomogeneityTreatment,
    build_narrative_homogeneity_sweep,
)


def _agent_ids(count: int = 8) -> tuple[str, ...]:
    return tuple(f"agent-{index:04d}" for index in range(count))


@pytest.mark.parametrize(
    ("homogeneity", "focal", "opposing"),
    [
        (Decimal("0"), 4, 4),
        (Decimal("0.25"), 5, 3),
        (Decimal("0.50"), 6, 2),
        (Decimal("0.75"), 7, 1),
        (Decimal("1"), 8, 0),
    ],
)
def test_eight_agent_grid_has_exact_directional_concentration(
    homogeneity: Decimal,
    focal: int,
    opposing: int,
) -> None:
    treatment = NarrativeHomogeneityTreatment(
        "h",
        _agent_ids(),
        homogeneity,
        NarrativeDirection.BULLISH,
    )

    assert treatment.focal_count == focal
    assert treatment.opposing_count == opposing
    assert treatment.assigned_directional_concentration == homogeneity


def test_zero_is_balanced_and_one_is_fully_focal() -> None:
    balanced = NarrativeHomogeneityTreatment(
        "balanced",
        _agent_ids(),
        Decimal("0"),
        NarrativeDirection.BULLISH,
    )
    homogeneous = NarrativeHomogeneityTreatment(
        "homogeneous",
        _agent_ids(),
        Decimal("1"),
        NarrativeDirection.BULLISH,
    )

    assert balanced.focal_agent_ids == _agent_ids()[:4]
    assert balanced.opposing_agent_ids == _agent_ids()[4:]
    assert homogeneous.focal_agent_ids == _agent_ids()
    assert homogeneous.opposing_agent_ids == ()


def test_assignment_is_canonical_and_nested_across_homogeneity() -> None:
    reversed_ids = tuple(reversed(_agent_ids()))
    sweep = build_narrative_homogeneity_sweep(
        reversed_ids,
        homogeneities=(
            Decimal("0"),
            Decimal("0.25"),
            Decimal("0.50"),
            Decimal("0.75"),
            Decimal("1"),
        ),
        focal_direction=NarrativeDirection.BULLISH,
    )

    assert all(treatment.agent_ids == _agent_ids() for treatment in sweep)
    for lower, higher in pairwise(sweep):
        assert set(lower.focal_agent_ids) < set(higher.focal_agent_ids)


def test_treatment_builds_equal_strength_opposing_narratives_and_exposures() -> None:
    treatment = NarrativeHomogeneityTreatment(
        "treatment",
        _agent_ids(),
        Decimal("0.5"),
        NarrativeDirection.BEARISH,
        strength=Decimal("0.8"),
        confidence=Decimal("0.9"),
        exposure_weight=Decimal("0.7"),
        active_from=2,
        active_until=5,
    )

    focal, opposing = treatment.narratives
    assert focal.direction is NarrativeDirection.BEARISH
    assert opposing.direction is NarrativeDirection.BULLISH
    assert focal.strength == opposing.strength == Decimal("0.8")
    assert focal.confidence == opposing.confidence == Decimal("0.9")
    assert focal.active_from == opposing.active_from == 2
    assert focal.active_until == opposing.active_until == 5

    assert len(treatment.exposures) == 8
    assert all(exposure.exposure_weight == Decimal("0.7") for exposure in treatment.exposures)
    assert all(isinstance(item, NarrativeAgentAssignment) for item in treatment.assignments)


def test_shared_policy_implements_agent_specific_assignment() -> None:
    treatment = NarrativeHomogeneityTreatment(
        "treatment",
        _agent_ids(),
        Decimal("0.5"),
        NarrativeDirection.BULLISH,
    )
    policy = treatment.policy(quantity=Decimal("1"))

    from abmforge_finance import MarketObservation

    observation = MarketObservation(
        step=0,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
    )

    assert (
        policy.decide(
            observation,
            agent_id=treatment.focal_agent_ids[0],
        ).side
        is Side.BUY
    )
    assert (
        policy.decide(
            observation,
            agent_id=treatment.opposing_agent_ids[0],
        ).side
        is Side.SELL
    )


@pytest.mark.parametrize(
    "homogeneity",
    [Decimal("-0.1"), Decimal("1.1")],
)
def test_homogeneity_must_be_unit_interval(homogeneity: Decimal) -> None:
    with pytest.raises(InvalidNarrativeTreatmentError, match="homogeneity"):
        NarrativeHomogeneityTreatment(
            "bad",
            _agent_ids(),
            homogeneity,
            NarrativeDirection.BULLISH,
        )


def test_non_representable_homogeneity_is_rejected_without_rounding() -> None:
    with pytest.raises(InvalidNarrativeTreatmentError, match="not exactly representable"):
        NarrativeHomogeneityTreatment(
            "bad",
            _agent_ids(6),
            Decimal("0.25"),
            NarrativeDirection.BULLISH,
        )

    with pytest.raises(InvalidNarrativeTreatmentError, match="not exactly representable"):
        NarrativeHomogeneityTreatment(
            "bad",
            _agent_ids(5),
            Decimal("0"),
            NarrativeDirection.BULLISH,
        )


def test_treatment_rejects_neutral_focal_direction_and_bad_agent_population() -> None:
    with pytest.raises(InvalidNarrativeTreatmentError, match="BULLISH or BEARISH"):
        NarrativeHomogeneityTreatment(
            "bad",
            _agent_ids(),
            Decimal("0"),
            NarrativeDirection.NEUTRAL,
        )

    with pytest.raises(InvalidNarrativeTreatmentError, match="at least two"):
        NarrativeHomogeneityTreatment(
            "bad",
            ("only-one",),
            Decimal("1"),
            NarrativeDirection.BULLISH,
        )

    with pytest.raises(InvalidNarrativeTreatmentError, match="unique"):
        NarrativeHomogeneityTreatment(
            "bad",
            ("a", "a"),
            Decimal("1"),
            NarrativeDirection.BULLISH,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("strength", Decimal("0")),
        ("confidence", Decimal("0")),
        ("exposure_weight", Decimal("0")),
        ("strength", Decimal("1.1")),
    ],
)
def test_directional_signal_scales_must_be_positive_unit_interval(
    field: str,
    value: Decimal,
) -> None:
    with pytest.raises(InvalidNarrativeTreatmentError):
        if field == "strength":
            NarrativeHomogeneityTreatment(
                "bad",
                _agent_ids(),
                Decimal("0"),
                NarrativeDirection.BULLISH,
                strength=value,
                confidence=Decimal("1"),
                exposure_weight=Decimal("1"),
            )
        elif field == "confidence":
            NarrativeHomogeneityTreatment(
                "bad",
                _agent_ids(),
                Decimal("0"),
                NarrativeDirection.BULLISH,
                strength=Decimal("1"),
                confidence=value,
                exposure_weight=Decimal("1"),
            )
        else:
            NarrativeHomogeneityTreatment(
                "bad",
                _agent_ids(),
                Decimal("0"),
                NarrativeDirection.BULLISH,
                strength=Decimal("1"),
                confidence=Decimal("1"),
                exposure_weight=value,
            )


def test_sweep_rejects_duplicate_or_empty_homogeneity_grid() -> None:
    with pytest.raises(InvalidNarrativeTreatmentError, match="non-empty"):
        build_narrative_homogeneity_sweep(
            _agent_ids(),
            homogeneities=(),
            focal_direction=NarrativeDirection.BULLISH,
        )

    with pytest.raises(InvalidNarrativeTreatmentError, match="unique"):
        build_narrative_homogeneity_sweep(
            _agent_ids(),
            homogeneities=(Decimal("0"), Decimal("0")),
            focal_direction=NarrativeDirection.BULLISH,
        )


def test_sweep_treatment_ids_are_canonical() -> None:
    sweep = build_narrative_homogeneity_sweep(
        _agent_ids(),
        homogeneities=(Decimal("0.00"), Decimal("0.50"), Decimal("1.00")),
        focal_direction=NarrativeDirection.BULLISH,
        treatment_prefix="H",
    )

    assert tuple(item.treatment_id for item in sweep) == ("H=0", "H=0.5", "H=1")
