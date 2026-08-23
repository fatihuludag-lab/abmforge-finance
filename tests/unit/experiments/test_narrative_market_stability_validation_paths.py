"""Validation-path coverage for narrative market-stability contracts."""

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
from abmforge_finance.recording import FinanceResearchDataset, MarketStateRecord


def _agent_ids() -> tuple[str, ...]:
    return tuple(f"agent-{index:04d}" for index in range(8))


def _treatment(
    homogeneity: Decimal = Decimal("0"),
    *,
    treatment_id: str | None = None,
    active_from: int = 0,
    active_until: int = 2,
) -> NarrativeHomogeneityTreatment:
    return NarrativeHomogeneityTreatment(
        treatment_id or f"H={homogeneity}",
        _agent_ids(),
        homogeneity,
        NarrativeDirection.BULLISH,
        active_from=active_from,
        active_until=active_until,
    )


def _market_state(period: int = 0) -> MarketStateRecord:
    return MarketStateRecord(
        period=period,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
        best_bid=Decimal("99"),
        best_ask=Decimal("101"),
        mid_price=Decimal("100"),
        spread=Decimal("2"),
        bid_depth=Decimal("10"),
        ask_depth=Decimal("10"),
        imbalance=None,
        order_count=2,
        last_trade_price=None,
        price_change=None,
        fee_balance=Decimal("0"),
    )


@pytest.mark.parametrize("start_step", [-1, True])
def test_direction_schedule_rejects_invalid_start_steps(
    start_step: int,
) -> None:
    with pytest.raises(InvalidNarrativeStabilityError, match="start_step"):
        NarrativeDirectionSchedule(
            (NarrativeDirection.BULLISH,),
            start_step=start_step,
        )


def test_direction_schedule_rejects_non_tuple_direction_container() -> None:
    with pytest.raises(InvalidNarrativeStabilityError, match="non-empty tuple"):
        NarrativeDirectionSchedule(
            [NarrativeDirection.BULLISH],  # type: ignore[arg-type]
        )


def test_direction_schedule_rejects_wrong_treatment_type() -> None:
    schedule = NarrativeDirectionSchedule((NarrativeDirection.BULLISH,))

    with pytest.raises(TypeError, match="NarrativeHomogeneityTreatment"):
        schedule.narratives_for(object())  # type: ignore[arg-type]


def test_direction_schedule_rejects_shifted_active_window() -> None:
    treatment = _treatment(active_from=0, active_until=2)
    schedule = NarrativeDirectionSchedule(
        (
            NarrativeDirection.BULLISH,
            NarrativeDirection.BEARISH,
        ),
        start_step=1,
    )

    with pytest.raises(InvalidNarrativeStabilityError, match="active window"):
        schedule.narratives_for(treatment)


@pytest.mark.parametrize(
    ("side_reference", "spread_reference"),
    [
        (Decimal("NaN"), Decimal("2")),
        (Decimal("-1"), Decimal("2")),
        (Decimal("10"), Decimal("NaN")),
        (Decimal("10"), Decimal("0")),
        (Decimal("10"), Decimal("-1")),
    ],
)
def test_evaluator_rejects_nonpositive_or_nonfinite_references(
    side_reference: Decimal,
    spread_reference: Decimal,
) -> None:
    with pytest.raises(InvalidNarrativeStabilityError):
        evaluate_narrative_market_stability(
            FinanceResearchDataset(),
            _treatment(),
            reference_side_depth=side_reference,
            reference_spread=spread_reference,
        )


def test_evaluator_requires_market_state_inside_active_window() -> None:
    dataset = FinanceResearchDataset(
        market_states=(_market_state(period=5),),
    )

    with pytest.raises(
        InvalidNarrativeStabilityError,
        match="no market states",
    ):
        evaluate_narrative_market_stability(
            dataset,
            _treatment(active_from=0, active_until=2),
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )


def test_evaluator_supports_no_treatment_decisions_or_executions() -> None:
    dataset = FinanceResearchDataset(
        market_states=(_market_state(),),
    )

    outcome = evaluate_narrative_market_stability(
        dataset,
        _treatment(),
        reference_side_depth=Decimal("10"),
        reference_spread=Decimal("2"),
    )

    assert outcome.active_period_count == 1
    assert outcome.mean_decision_concentration is None
    assert outcome.mean_accepted_order_concentration is None
    assert outcome.mean_executed_flow_concentration is None
    assert outcome.treatment_rejected_order_count == 0
    assert outcome.treatment_executed_volume == Decimal("0")
    assert outcome.market_trade_volume == Decimal("0")


def test_sweep_rejects_empty_dataset_tuple() -> None:
    with pytest.raises(InvalidNarrativeStabilityError, match="datasets"):
        evaluate_narrative_market_stability_sweep(
            (),
            (),
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )


def test_sweep_rejects_empty_treatment_tuple() -> None:
    with pytest.raises(InvalidNarrativeStabilityError, match="treatments"):
        evaluate_narrative_market_stability_sweep(
            (FinanceResearchDataset(),),
            (),
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )


def test_sweep_rejects_invalid_dataset_members() -> None:
    with pytest.raises(
        InvalidNarrativeStabilityError,
        match="FinanceResearchDataset",
    ):
        evaluate_narrative_market_stability_sweep(
            (object(),),  # type: ignore[arg-type]
            (_treatment(),),
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )


def test_sweep_rejects_invalid_treatment_members() -> None:
    with pytest.raises(
        InvalidNarrativeStabilityError,
        match="NarrativeHomogeneityTreatment",
    ):
        evaluate_narrative_market_stability_sweep(
            (FinanceResearchDataset(),),
            (object(),),  # type: ignore[arg-type]
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )


def test_sweep_rejects_duplicate_homogeneity_values() -> None:
    dataset = FinanceResearchDataset()
    treatments = (
        _treatment(Decimal("0"), treatment_id="control-a"),
        _treatment(Decimal("0"), treatment_id="control-b"),
    )

    with pytest.raises(InvalidNarrativeStabilityError, match="must be unique"):
        evaluate_narrative_market_stability_sweep(
            (dataset, dataset),
            treatments,
            reference_side_depth=Decimal("10"),
            reference_spread=Decimal("2"),
        )
