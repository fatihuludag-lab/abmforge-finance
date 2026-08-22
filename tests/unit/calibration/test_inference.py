"""Tests for paired calibration inference and Student-t uncertainty."""

from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    CalibrationRunResult,
    CalibrationRunSpec,
    CalibrationScenario,
    paired_treatment_contrast,
    student_t_critical_value,
    summarize_calibration_runs,
    summarize_contrast_region,
)
from abmforge_finance.exceptions import CalibrationInferenceError


def _experiment(
    treatment_id: str,
    parameter_value: str,
    trade_counts: tuple[int, ...],
    *,
    seeds: tuple[int, ...] | None = None,
    scenario_id: str = "paired-test",
    parameter_key: str = "x",
    undefined_last_trade: bool = True,
) -> CalibrationExperimentResult:
    actual_seeds = seeds or tuple(range(101, 101 + len(trade_counts)))
    scenario = CalibrationScenario(
        scenario_id,
        treatment_id,
        2,
        ((parameter_key, parameter_value),),
    )
    runs = tuple(
        CalibrationRunResult(
            spec=CalibrationRunSpec(scenario, index, seed),
            dataset_schema_version="1.1",
            participant_count=3,
            decision_count=6,
            cancellation_count=2,
            order_count=6,
            rejected_order_count=0,
            trade_count=trade_count,
            trade_volume=Decimal(trade_count),
            mid_realized_volatility=0.0,
            last_trade_realized_volatility=(None if undefined_last_trade else float(trade_count)),
            maximum_drawdown=Decimal("0"),
            mean_relative_spread=Decimal("0.02"),
            mean_total_depth=Decimal("3"),
            mean_absolute_relative_dislocation=Decimal("0"),
            mean_decision_sign_concentration=Decimal("1"),
        )
        for index, (seed, trade_count) in enumerate(zip(actual_seeds, trade_counts, strict=True))
    )
    return CalibrationExperimentResult(
        scenario=scenario,
        runs=runs,
        summary=summarize_calibration_runs(runs),
    )


@pytest.mark.parametrize(
    ("df", "expected"),
    [
        (1, 12.7062047362),
        (2, 4.3026527297),
        (4, 2.7764451052),
        (9, 2.2621571628),
        (29, 2.0452296421),
    ],
)
def test_student_t_reference_critical_values(df: int, expected: float) -> None:
    assert student_t_critical_value(df) == pytest.approx(expected, rel=1e-10)


@pytest.mark.parametrize(
    ("df", "level"),
    [
        (0, 0.95),
        (True, 0.95),
        (2, 0.0),
        (2, 1.0),
        (2, float("nan")),
    ],
)
def test_student_t_rejects_invalid_inputs(df: object, level: float) -> None:
    with pytest.raises(CalibrationInferenceError):
        student_t_critical_value(
            df,  # type: ignore[arg-type]
            confidence_level=level,
        )


def test_paired_contrast_uses_treatment_minus_control_and_student_t_ci() -> None:
    control = _experiment("control", "0", (1, 2, 3, 4, 5))
    treatment = _experiment("treatment", "1", (2, 4, 4, 7, 6))

    contrast = paired_treatment_contrast(
        control,
        treatment,
        metric_name="trade_count",
    )

    assert contrast.differences == (1.0, 2.0, 1.0, 3.0, 1.0)
    assert contrast.mean_difference == pytest.approx(1.6)
    assert contrast.sample_std_difference == pytest.approx(0.8944271909999159)
    assert contrast.standard_error == pytest.approx(0.4)
    assert contrast.critical_value == pytest.approx(2.7764451052)
    assert contrast.confidence_interval_lower == pytest.approx(0.4894219579)
    assert contrast.confidence_interval_upper == pytest.approx(2.7105780421)
    assert contrast.excludes_zero
    assert contrast.pair_count == 5
    assert contrast.changed_parameters == (("x", "0", "1"),)


def test_zero_variance_paired_difference_has_degenerate_interval() -> None:
    control = _experiment("control", "0", (1, 2, 3))
    treatment = _experiment("treatment", "1", (3, 4, 5))

    contrast = paired_treatment_contrast(
        control,
        treatment,
        metric_name="trade_count",
        confidence_level=0.90,
    )

    assert contrast.differences == (2.0, 2.0, 2.0)
    assert contrast.sample_std_difference == 0.0
    assert contrast.standard_error == 0.0
    assert contrast.confidence_interval_lower == 2.0
    assert contrast.confidence_interval_upper == 2.0
    assert contrast.excludes_zero


def test_contrast_rejects_undefined_metric_and_unknown_metric() -> None:
    control = _experiment("control", "0", (1, 2))
    treatment = _experiment("treatment", "1", (2, 3))

    with pytest.raises(CalibrationInferenceError, match="undefined"):
        paired_treatment_contrast(
            control,
            treatment,
            metric_name="last_trade_realized_volatility",
        )

    with pytest.raises(CalibrationInferenceError, match="unknown"):
        paired_treatment_contrast(
            control,
            treatment,
            metric_name="not-a-metric",
        )


def test_contrast_rejects_seed_and_scenario_contract_mismatches() -> None:
    control = _experiment("control", "0", (1, 2), seeds=(11, 12))

    with pytest.raises(CalibrationInferenceError, match="seed tuples"):
        paired_treatment_contrast(
            control,
            _experiment("treatment", "1", (2, 3), seeds=(11, 13)),
            metric_name="trade_count",
        )

    with pytest.raises(CalibrationInferenceError, match="scenario_id"):
        paired_treatment_contrast(
            control,
            _experiment(
                "treatment",
                "1",
                (2, 3),
                seeds=(11, 12),
                scenario_id="other",
            ),
            metric_name="trade_count",
        )

    with pytest.raises(CalibrationInferenceError, match="parameter keys"):
        paired_treatment_contrast(
            control,
            _experiment(
                "treatment",
                "1",
                (2, 3),
                seeds=(11, 12),
                parameter_key="y",
            ),
            metric_name="trade_count",
        )


def test_contrast_requires_two_pairs_changed_parameter_and_valid_metric_name() -> None:
    single_control = _experiment("control", "0", (1,), seeds=(11,))
    single_treatment = _experiment("treatment", "1", (2,), seeds=(11,))
    with pytest.raises(CalibrationInferenceError, match="at least two"):
        paired_treatment_contrast(
            single_control,
            single_treatment,
            metric_name="trade_count",
        )

    control = _experiment("control", "0", (1, 2))
    relabel = _experiment("relabel", "0", (2, 3))
    with pytest.raises(CalibrationInferenceError, match="differ"):
        paired_treatment_contrast(control, relabel, metric_name="trade_count")

    with pytest.raises(CalibrationInferenceError, match="metric_name"):
        paired_treatment_contrast(control, relabel, metric_name="")


def test_region_summary_reports_directional_consistency() -> None:
    control = _experiment("control", "0", (1, 2, 3))
    first = paired_treatment_contrast(
        control,
        _experiment("treatment-a", "1", (2, 3, 4)),
        metric_name="trade_count",
    )
    second = paired_treatment_contrast(
        control,
        _experiment("treatment-b", "2", (3, 4, 5)),
        metric_name="trade_count",
    )

    region = summarize_contrast_region((first, second))

    assert region.contrast_count == 2
    assert region.positive_mean_count == 2
    assert region.negative_mean_count == 0
    assert region.zero_mean_count == 0
    assert region.intervals_excluding_zero_count == 2
    assert region.direction_consistency == "positive"
    assert region.minimum_mean_difference == 1.0
    assert region.maximum_mean_difference == 2.0


def test_region_summary_rejects_empty_and_duplicate_treatments() -> None:
    with pytest.raises(CalibrationInferenceError, match="non-empty"):
        summarize_contrast_region(())

    control = _experiment("control", "0", (1, 2, 3))
    contrast = paired_treatment_contrast(
        control,
        _experiment("treatment", "1", (2, 3, 4)),
        metric_name="trade_count",
    )
    with pytest.raises(CalibrationInferenceError, match="unique"):
        summarize_contrast_region((contrast, contrast))
