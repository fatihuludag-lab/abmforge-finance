"""Failure-path and robustness-region coverage for calibration inference."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    CalibrationRunResult,
    CalibrationRunSpec,
    CalibrationScenario,
    CalibrationSummary,
    paired_treatment_contrast,
    student_t_critical_value,
    summarize_calibration_runs,
    summarize_contrast_region,
)
from abmforge_finance.exceptions import CalibrationInferenceError


def _experiment(
    *,
    treatment_id: str,
    parameter_value: str,
    seeds: tuple[int, ...] = (11, 12),
    trade_counts: tuple[int, ...] = (1, 2),
    scenario_id: str = "validation",
    periods: int = 2,
) -> CalibrationExperimentResult:
    scenario = CalibrationScenario(
        scenario_id,
        treatment_id,
        periods,
        (("x", parameter_value),),
    )
    runs = tuple(
        CalibrationRunResult(
            spec=CalibrationRunSpec(scenario, replicate, seed),
            dataset_schema_version="1.1",
            participant_count=3,
            decision_count=6,
            cancellation_count=2,
            order_count=6,
            rejected_order_count=0,
            trade_count=trade_count,
            trade_volume=Decimal(trade_count),
            mid_realized_volatility=0.0,
            last_trade_realized_volatility=float(trade_count),
            maximum_drawdown=Decimal("0"),
            mean_relative_spread=Decimal("0.02"),
            mean_total_depth=Decimal("3"),
            mean_absolute_relative_dislocation=Decimal("0"),
            mean_decision_sign_concentration=Decimal("1"),
        )
        for replicate, (seed, trade_count) in enumerate(zip(seeds, trade_counts, strict=True))
    )
    return CalibrationExperimentResult(
        scenario=scenario,
        runs=runs,
        summary=summarize_calibration_runs(runs),
    )


def _valid_pair() -> tuple[
    CalibrationExperimentResult,
    CalibrationExperimentResult,
]:
    control = _experiment(treatment_id="control", parameter_value="0")
    treatment = _experiment(
        treatment_id="treatment",
        parameter_value="1",
        trade_counts=(2, 4),
    )
    return control, treatment


def test_student_t_additional_public_validation_paths() -> None:
    with pytest.raises(CalibrationInferenceError, match="real number"):
        student_t_critical_value(
            2,
            confidence_level="0.95",  # type: ignore[arg-type]
        )

    with pytest.raises(CalibrationInferenceError, match="positive integer"):
        student_t_critical_value(
            "2",  # type: ignore[arg-type]
            confidence_level=0.95,
        )

    with pytest.raises(CalibrationInferenceError, match="between 0 and 1"):
        student_t_critical_value(2, confidence_level=float("inf"))


def test_paired_contrast_rejects_wrong_experiment_types() -> None:
    control, treatment = _valid_pair()

    with pytest.raises(TypeError, match="control"):
        paired_treatment_contrast(
            object(),  # type: ignore[arg-type]
            treatment,
            metric_name="trade_count",
        )

    with pytest.raises(TypeError, match="treatment"):
        paired_treatment_contrast(
            control,
            object(),  # type: ignore[arg-type]
            metric_name="trade_count",
        )


def test_experiment_validation_rejects_empty_runs_and_summary_mismatch() -> None:
    control, treatment = _valid_pair()

    empty = CalibrationExperimentResult(
        scenario=control.scenario,
        runs=(),
        summary=CalibrationSummary(
            scenario=control.scenario,
            seeds=(),
            metrics=(),
        ),
    )
    with pytest.raises(CalibrationInferenceError, match="at least one"):
        paired_treatment_contrast(
            empty,
            treatment,
            metric_name="trade_count",
        )

    other_scenario = CalibrationScenario(
        "validation",
        "other-summary",
        2,
        (("x", "9"),),
    )
    mismatched_summary = replace(
        control,
        summary=replace(control.summary, scenario=other_scenario),
    )
    with pytest.raises(CalibrationInferenceError, match="summary scenario"):
        paired_treatment_contrast(
            mismatched_summary,
            treatment,
            metric_name="trade_count",
        )


def test_experiment_validation_rejects_run_scenario_replicate_and_seed_mismatch() -> None:
    control, treatment = _valid_pair()

    foreign_scenario = CalibrationScenario(
        "validation",
        "foreign",
        2,
        (("x", "7"),),
    )
    foreign_run = replace(
        control.runs[0],
        spec=replace(control.runs[0].spec, scenario=foreign_scenario),
    )
    mismatched_run_scenario = replace(
        control,
        runs=(foreign_run, control.runs[1]),
    )
    with pytest.raises(CalibrationInferenceError, match="replicate scenario"):
        paired_treatment_contrast(
            mismatched_run_scenario,
            treatment,
            metric_name="trade_count",
        )

    noncontiguous = replace(
        control,
        runs=(
            control.runs[0],
            replace(
                control.runs[1],
                spec=replace(control.runs[1].spec, replicate=2),
            ),
        ),
    )
    with pytest.raises(CalibrationInferenceError, match="contiguous"):
        paired_treatment_contrast(
            noncontiguous,
            treatment,
            metric_name="trade_count",
        )

    seed_mismatch = replace(
        control,
        runs=(
            control.runs[0],
            replace(
                control.runs[1],
                spec=replace(control.runs[1].spec, seed=99),
            ),
        ),
    )
    with pytest.raises(CalibrationInferenceError, match="summary seed"):
        paired_treatment_contrast(
            seed_mismatch,
            treatment,
            metric_name="trade_count",
        )


def test_paired_contrast_rejects_horizon_and_treatment_identifier_mismatches() -> None:
    control, _ = _valid_pair()

    different_horizon = _experiment(
        treatment_id="treatment",
        parameter_value="1",
        periods=3,
    )
    with pytest.raises(CalibrationInferenceError, match="simulation horizon"):
        paired_treatment_contrast(
            control,
            different_horizon,
            metric_name="trade_count",
        )

    same_identifier = _experiment(
        treatment_id="control",
        parameter_value="1",
    )
    with pytest.raises(CalibrationInferenceError, match="distinct treatment_id"):
        paired_treatment_contrast(
            control,
            same_identifier,
            metric_name="trade_count",
        )


def test_paired_contrast_rejects_non_finite_metric_without_dropping_pair() -> None:
    control, treatment = _valid_pair()

    bad_run = replace(
        treatment.runs[1],
        mid_realized_volatility=float("nan"),
    )
    bad_treatment = replace(
        treatment,
        runs=(treatment.runs[0], bad_run),
    )

    with pytest.raises(CalibrationInferenceError, match="finite"):
        paired_treatment_contrast(
            control,
            bad_treatment,
            metric_name="mid_realized_volatility",
        )


def test_region_summary_rejects_wrong_container_and_item_types() -> None:
    with pytest.raises(CalibrationInferenceError, match="non-empty tuple"):
        summarize_contrast_region([])  # type: ignore[arg-type]

    with pytest.raises(CalibrationInferenceError, match="PairedTreatmentContrast"):
        summarize_contrast_region((object(),))  # type: ignore[arg-type]


def test_region_summary_rejects_metric_control_and_confidence_mismatches() -> None:
    control, treatment = _valid_pair()
    base = paired_treatment_contrast(
        control,
        treatment,
        metric_name="trade_count",
    )

    with pytest.raises(CalibrationInferenceError, match="same metric"):
        summarize_contrast_region(
            (
                base,
                replace(
                    base,
                    treatment_scenario=replace(
                        base.treatment_scenario,
                        treatment_id="metric-other",
                    ),
                    metric_name="order_count",
                ),
            )
        )

    with pytest.raises(CalibrationInferenceError, match="control scenario"):
        summarize_contrast_region(
            (
                base,
                replace(
                    base,
                    treatment_scenario=replace(
                        base.treatment_scenario,
                        treatment_id="control-other-treatment",
                    ),
                    control_scenario=replace(
                        base.control_scenario,
                        scenario_id="other-control",
                    ),
                ),
            )
        )

    with pytest.raises(CalibrationInferenceError, match="confidence level"):
        summarize_contrast_region(
            (
                base,
                replace(
                    base,
                    treatment_scenario=replace(
                        base.treatment_scenario,
                        treatment_id="confidence-other",
                    ),
                    confidence_level=0.90,
                ),
            )
        )


def test_region_summary_covers_negative_zero_and_mixed_directions() -> None:
    control, treatment = _valid_pair()
    positive = paired_treatment_contrast(
        control,
        treatment,
        metric_name="trade_count",
    )

    negative = replace(
        positive,
        treatment_scenario=replace(
            positive.treatment_scenario,
            treatment_id="negative",
        ),
        mean_difference=-1.0,
        confidence_interval_lower=-2.0,
        confidence_interval_upper=-0.5,
    )
    zero = replace(
        positive,
        treatment_scenario=replace(
            positive.treatment_scenario,
            treatment_id="zero",
        ),
        mean_difference=0.0,
        confidence_interval_lower=-1.0,
        confidence_interval_upper=1.0,
    )

    negative_region = summarize_contrast_region((negative,))
    assert negative_region.direction_consistency == "negative"
    assert negative_region.negative_mean_count == 1

    zero_region = summarize_contrast_region((zero,))
    assert zero_region.direction_consistency == "zero"
    assert zero_region.zero_mean_count == 1
    assert zero_region.intervals_excluding_zero_count == 0

    mixed_region = summarize_contrast_region((positive, negative, zero))
    assert mixed_region.direction_consistency == "mixed"
    assert mixed_region.positive_mean_count == 1
    assert mixed_region.negative_mean_count == 1
    assert mixed_region.zero_mean_count == 1
