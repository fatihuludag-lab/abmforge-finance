"""Additional validation-path coverage for calibration robustness."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    CalibrationRunResult,
    CalibrationRunSpec,
    CalibrationScenario,
    RobustnessClassification,
    TreatmentFamilyAudit,
    audit_parameter_sweep,
    build_baseline_ecology_audit,
    summarize_calibration_runs,
)
from abmforge_finance.exceptions import (
    CalibrationInferenceError,
    CalibrationRobustnessError,
)


def _experiment(
    treatment_id: str,
    parameter_name: str,
    parameter_value: str,
    *,
    seeds: tuple[int, ...] = (11, 12, 13),
    trade_counts: tuple[int, ...] = (10, 10, 10),
) -> CalibrationExperimentResult:
    scenario = CalibrationScenario(
        "robustness-validation",
        treatment_id,
        2,
        ((parameter_name, parameter_value),),
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


def _valid_family() -> TreatmentFamilyAudit:
    return audit_parameter_sweep(
        (
            _experiment("control", "x", "1"),
            _experiment("x=2", "x", "2", trade_counts=(12, 12, 12)),
            _experiment("x=3", "x", "3", trade_counts=(14, 14, 14)),
        ),
        control_index=0,
        family_name="valid-family",
        parameter_name="x",
        metric_name="trade_count",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("family_name", ""),
        ("family_name", "   "),
        ("parameter_name", ""),
        ("metric_name", ""),
    ],
)
def test_family_audit_rejects_empty_names(field: str, value: str) -> None:
    experiments = (
        _experiment("control", "x", "1"),
        _experiment("treatment", "x", "2", trade_counts=(12, 12, 12)),
    )

    with pytest.raises(CalibrationRobustnessError, match="non-empty"):
        if field == "family_name":
            audit_parameter_sweep(
                experiments,
                control_index=0,
                family_name=value,
                parameter_name="x",
                metric_name="trade_count",
                minimum_contrasts=1,
            )
        elif field == "parameter_name":
            audit_parameter_sweep(
                experiments,
                control_index=0,
                family_name="family",
                parameter_name=value,
                metric_name="trade_count",
                minimum_contrasts=1,
            )
        else:
            audit_parameter_sweep(
                experiments,
                control_index=0,
                family_name="family",
                parameter_name="x",
                metric_name=value,
                minimum_contrasts=1,
            )


@pytest.mark.parametrize("minimum", [0, True, "2"])
def test_family_audit_rejects_invalid_minimum_contrasts(minimum: object) -> None:
    with pytest.raises(CalibrationRobustnessError, match="positive integer"):
        audit_parameter_sweep(
            (
                _experiment("control", "x", "1"),
                _experiment("treatment", "x", "2", trade_counts=(12, 12, 12)),
            ),
            control_index=0,
            family_name="family",
            parameter_name="x",
            metric_name="trade_count",
            minimum_contrasts=minimum,  # type: ignore[arg-type]
        )


def test_family_audit_rejects_non_experiment_items_and_boolean_control_index() -> None:
    control = _experiment("control", "x", "1")

    with pytest.raises(CalibrationRobustnessError, match="CalibrationExperimentResult"):
        audit_parameter_sweep(
            (control, object()),  # type: ignore[arg-type]
            control_index=0,
            family_name="family",
            parameter_name="x",
            metric_name="trade_count",
        )

    with pytest.raises(CalibrationRobustnessError, match="control_index"):
        audit_parameter_sweep(
            (
                control,
                _experiment("treatment", "x", "2", trade_counts=(12, 12, 12)),
            ),
            control_index=True,
            family_name="family",
            parameter_name="x",
            metric_name="trade_count",
        )


def test_family_audit_preserves_inference_errors_for_invalid_metrics() -> None:
    control = _experiment("control", "x", "1")
    treatment = _experiment("treatment", "x", "2", trade_counts=(12, 12, 12))

    with pytest.raises(CalibrationInferenceError, match="unknown calibration metric"):
        audit_parameter_sweep(
            (control, treatment),
            control_index=0,
            family_name="family",
            parameter_name="x",
            metric_name="not-a-metric",
            minimum_contrasts=1,
        )

    undefined_run = replace(
        treatment.runs[0],
        last_trade_realized_volatility=None,
    )
    undefined_treatment = replace(
        treatment,
        runs=(undefined_run, *treatment.runs[1:]),
    )
    with pytest.raises(CalibrationInferenceError, match="undefined"):
        audit_parameter_sweep(
            (control, undefined_treatment),
            control_index=0,
            family_name="family",
            parameter_name="x",
            metric_name="last_trade_realized_volatility",
            minimum_contrasts=1,
        )

    nonfinite_run = replace(
        treatment.runs[0],
        last_trade_realized_volatility=float("inf"),
    )
    nonfinite_treatment = replace(
        treatment,
        runs=(nonfinite_run, *treatment.runs[1:]),
    )
    with pytest.raises(CalibrationInferenceError, match="finite"):
        audit_parameter_sweep(
            (control, nonfinite_treatment),
            control_index=0,
            family_name="family",
            parameter_name="x",
            metric_name="last_trade_realized_volatility",
            minimum_contrasts=1,
        )


def test_nonfinite_numeric_parameter_is_treated_as_undefined_sensitivity() -> None:
    audit = audit_parameter_sweep(
        (
            _experiment("control", "x", "1"),
            _experiment("treatment", "x", "inf", trade_counts=(12, 12, 12)),
        ),
        control_index=0,
        family_name="family",
        parameter_name="x",
        metric_name="trade_count",
        minimum_contrasts=1,
    )

    sensitivity = audit.sensitivities[0]
    assert not sensitivity.defined
    assert sensitivity.undefined_reason == "non_numeric_parameter"


def test_baseline_audit_rejects_empty_invalid_and_duplicate_requirements() -> None:
    family = _valid_family()

    with pytest.raises(CalibrationRobustnessError, match="family_audits"):
        build_baseline_ecology_audit(
            (),
            required_families=("valid-family",),
        )

    with pytest.raises(CalibrationRobustnessError, match="TreatmentFamilyAudit"):
        build_baseline_ecology_audit(
            (object(),),  # type: ignore[arg-type]
            required_families=("valid-family",),
        )

    with pytest.raises(CalibrationRobustnessError, match="required_families"):
        build_baseline_ecology_audit(
            (family,),
            required_families=(),
        )

    with pytest.raises(CalibrationRobustnessError, match="non-empty"):
        build_baseline_ecology_audit(
            (family,),
            required_families=("",),
        )

    with pytest.raises(CalibrationRobustnessError, match="unique"):
        build_baseline_ecology_audit(
            (family,),
            required_families=("valid-family", "valid-family"),
        )


def test_baseline_audit_rejects_empty_audit_id() -> None:
    family = _valid_family()

    with pytest.raises(CalibrationRobustnessError, match="audit_id"):
        build_baseline_ecology_audit(
            (family,),
            required_families=("valid-family",),
            audit_id="",
        )


def test_baseline_audit_records_mixed_family_without_marking_it_incomplete() -> None:
    mixed = audit_parameter_sweep(
        (
            _experiment("control", "x", "1"),
            _experiment("positive", "x", "2", trade_counts=(12, 12, 12)),
            _experiment("negative", "x", "3", trade_counts=(8, 8, 8)),
        ),
        control_index=0,
        family_name="mixed-family",
        parameter_name="x",
        metric_name="trade_count",
    )
    assert mixed.classification is RobustnessClassification.MIXED

    audit = build_baseline_ecology_audit(
        (mixed,),
        required_families=("mixed-family",),
    )

    assert audit.complete
    assert audit.mixed_families == ("mixed-family",)
    assert audit.insufficient_families == ()
