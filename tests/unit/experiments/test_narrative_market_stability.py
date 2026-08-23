"""Unit tests for narrative market-stability evaluation contracts."""

from decimal import Decimal

import pytest

from abmforge_finance import NarrativeDirection
from abmforge_finance.exceptions import InvalidNarrativeStabilityError
from abmforge_finance.experiments import (
    NarrativeDirectionSchedule,
    NarrativeHomogeneityTreatment,
    evaluate_narrative_market_stability,
    evaluate_narrative_market_stability_sweep,
)
from abmforge_finance.recording import FinanceResearchDataset


def _treatment(
    homogeneity: Decimal = Decimal("0"),
    *,
    strength: Decimal = Decimal("1"),
) -> NarrativeHomogeneityTreatment:
    return NarrativeHomogeneityTreatment(
        f"H={homogeneity}",
        tuple(f"agent-{index:04d}" for index in range(8)),
        homogeneity,
        NarrativeDirection.BULLISH,
        strength=strength,
        active_from=0,
        active_until=4,
    )


def test_direction_schedule_builds_opposing_time_varying_streams() -> None:
    treatment = _treatment()
    schedule = NarrativeDirectionSchedule(
        (
            NarrativeDirection.BULLISH,
            NarrativeDirection.BEARISH,
            NarrativeDirection.BULLISH,
            NarrativeDirection.BEARISH,
        )
    )

    states = schedule.narratives_for(treatment)

    assert schedule.end_step == 4
    assert len(states) == 8
    assert tuple(state.direction for state in states[::2]) == schedule.directions
    assert tuple(state.direction for state in states[1::2]) == (
        NarrativeDirection.BEARISH,
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
        NarrativeDirection.BULLISH,
    )


@pytest.mark.parametrize(
    "directions",
    [
        (),
        (NarrativeDirection.NEUTRAL,),
    ],
)
def test_direction_schedule_rejects_empty_or_neutral_paths(
    directions: tuple[NarrativeDirection, ...],
) -> None:
    with pytest.raises(InvalidNarrativeStabilityError):
        NarrativeDirectionSchedule(directions)


def test_direction_schedule_requires_exact_treatment_window_and_initial_direction() -> None:
    treatment = _treatment()

    with pytest.raises(InvalidNarrativeStabilityError, match="active window"):
        NarrativeDirectionSchedule(
            (NarrativeDirection.BULLISH,),
        ).narratives_for(treatment)

    with pytest.raises(InvalidNarrativeStabilityError, match="first scheduled"):
        NarrativeDirectionSchedule(
            (
                NarrativeDirection.BEARISH,
                NarrativeDirection.BULLISH,
                NarrativeDirection.BEARISH,
                NarrativeDirection.BULLISH,
            )
        ).narratives_for(treatment)


def test_evaluator_rejects_wrong_types_and_invalid_references() -> None:
    treatment = _treatment()

    with pytest.raises(TypeError, match="FinanceResearchDataset"):
        evaluate_narrative_market_stability(
            object(),  # type: ignore[arg-type]
            treatment,
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )

    with pytest.raises(TypeError, match="NarrativeHomogeneityTreatment"):
        evaluate_narrative_market_stability(
            FinanceResearchDataset(),
            object(),  # type: ignore[arg-type]
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )

    with pytest.raises(InvalidNarrativeStabilityError, match="reference_side_depth"):
        evaluate_narrative_market_stability(
            FinanceResearchDataset(),
            treatment,
            reference_side_depth=Decimal("0"),
            reference_spread=Decimal("2"),
        )


def test_sweep_rejects_length_mismatch_and_non_homogeneity_confounds() -> None:
    dataset = FinanceResearchDataset()

    with pytest.raises(InvalidNarrativeStabilityError, match="equal length"):
        evaluate_narrative_market_stability_sweep(
            (dataset,),
            (_treatment(), _treatment(Decimal("0.25"))),
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )

    with pytest.raises(InvalidNarrativeStabilityError, match="differ only"):
        evaluate_narrative_market_stability_sweep(
            (dataset, dataset),
            (
                _treatment(),
                _treatment(Decimal("0.25"), strength=Decimal("0.8")),
            ),
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )
