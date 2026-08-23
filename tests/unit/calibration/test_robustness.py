"""Unit tests for calibration robustness and sensitivity audits."""

from __future__ import annotations

from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    BaselineEcologyAudit,
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
from abmforge_finance.exceptions import CalibrationRobustnessError


def _experiment(
    treatment_id: str,
    parameter_value: str,
    trade_counts: tuple[int, ...],
    *,
    parameter_name: str = "x",
    second_parameter: tuple[str, str] | None = None,
    seeds: tuple[int, ...] = (11, 12, 13),
) -> CalibrationExperimentResult:
    parameters = [(parameter_name, parameter_value)]
    if second_parameter is not None:
        parameters.append(second_parameter)
    scenario = CalibrationScenario(
        "robustness-test",
        treatment_id,
        2,
        tuple(parameters),
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


def test_positive_family_audit_has_defined_unit_elasticities() -> None:
    experiments = (
        _experiment("control", "1", (10, 10, 10)),
        _experiment("x=2", "2", (20, 20, 20)),
        _experiment("x=4", "4", (40, 40, 40)),
    )

    audit = audit_parameter_sweep(
        experiments,
        control_index=0,
        family_name="scale",
        parameter_name="x",
        metric_name="trade_count",
    )

    assert isinstance(audit, TreatmentFamilyAudit)
    assert audit.classification is RobustnessClassification.ROBUST_POSITIVE
    assert audit.contrast_count == 2
    assert audit.all_individual_intervals_exclude_zero
    assert audit.individual_interval_exclusion_fraction == 1.0
    assert tuple(item.elasticity for item in audit.sensitivities) == (1.0, 1.0)
    assert all(item.defined for item in audit.sensitivities)


@pytest.mark.parametrize(
    ("treatment_counts", "expected"),
    [
        (
            ((8, 8, 8), (6, 6, 6)),
            RobustnessClassification.ROBUST_NEGATIVE,
        ),
        (
            ((10, 10, 10), (10, 10, 10)),
            RobustnessClassification.ROBUST_ZERO,
        ),
    ],
)
def test_family_direction_classification(
    treatment_counts: tuple[tuple[int, ...], tuple[int, ...]],
    expected: RobustnessClassification,
) -> None:
    audit = audit_parameter_sweep(
        (
            _experiment("control", "1", (10, 10, 10)),
            _experiment("x=2", "2", treatment_counts[0]),
            _experiment("x=3", "3", treatment_counts[1]),
        ),
        control_index=0,
        family_name="direction",
        parameter_name="x",
        metric_name="trade_count",
    )
    assert audit.classification is expected


def test_mixed_and_insufficient_classifications_are_explicit() -> None:
    mixed = audit_parameter_sweep(
        (
            _experiment("control", "1", (10, 10, 10)),
            _experiment("positive", "2", (12, 12, 12)),
            _experiment("negative", "3", (8, 8, 8)),
            _experiment("zero", "4", (10, 10, 10)),
        ),
        control_index=0,
        family_name="mixed",
        parameter_name="x",
        metric_name="trade_count",
    )
    assert mixed.classification is RobustnessClassification.MIXED

    insufficient = audit_parameter_sweep(
        (
            _experiment("control", "1", (10, 10, 10)),
            _experiment("only-treatment", "2", (12, 12, 12)),
        ),
        control_index=0,
        family_name="small-region",
        parameter_name="x",
        metric_name="trade_count",
    )
    assert insufficient.classification is RobustnessClassification.INSUFFICIENT


@pytest.mark.parametrize(
    ("control_parameter", "treatment_parameter", "control_counts", "reason"),
    [
        ("0", "1", (10, 10, 10), "zero_control_parameter"),
        ("1", "2", (0, 0, 0), "zero_control_metric"),
        ("low", "high", (10, 10, 10), "non_numeric_parameter"),
        ("1", "1.0", (10, 10, 10), "zero_numeric_parameter_change"),
    ],
)
def test_sensitivity_refuses_invalid_normalization_scales(
    control_parameter: str,
    treatment_parameter: str,
    control_counts: tuple[int, ...],
    reason: str,
) -> None:
    audit = audit_parameter_sweep(
        (
            _experiment("control", control_parameter, control_counts),
            _experiment("treatment", treatment_parameter, (12, 12, 12)),
        ),
        control_index=0,
        family_name="normalization",
        parameter_name="x",
        metric_name="trade_count",
        minimum_contrasts=1,
    )
    sensitivity = audit.sensitivities[0]
    assert not sensitivity.defined
    assert sensitivity.elasticity is None
    assert sensitivity.undefined_reason == reason


def test_family_audit_rejects_confounded_and_wrong_parameter_sweeps() -> None:
    control = _experiment(
        "control",
        "1",
        (10, 10, 10),
        second_parameter=("y", "1"),
    )
    confounded = _experiment(
        "confounded",
        "2",
        (12, 12, 12),
        second_parameter=("y", "2"),
    )
    with pytest.raises(CalibrationRobustnessError, match="exactly one"):
        audit_parameter_sweep(
            (control, confounded),
            control_index=0,
            family_name="confounded",
            parameter_name="x",
            metric_name="trade_count",
            minimum_contrasts=1,
        )

    with pytest.raises(CalibrationRobustnessError, match="parameter_name"):
        audit_parameter_sweep(
            (
                _experiment("control", "1", (10, 10, 10)),
                _experiment("treatment", "2", (12, 12, 12)),
            ),
            control_index=0,
            family_name="wrong-name",
            parameter_name="y",
            metric_name="trade_count",
            minimum_contrasts=1,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"experiments": (), "control_index": 0},
        {
            "experiments": (
                _experiment("control", "1", (10, 10, 10)),
                _experiment("treatment", "2", (12, 12, 12)),
            ),
            "control_index": -1,
        },
        {
            "experiments": (
                _experiment("control", "1", (10, 10, 10)),
                _experiment("treatment", "2", (12, 12, 12)),
            ),
            "control_index": 2,
        },
    ],
)
def test_family_audit_rejects_invalid_region_inputs(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(CalibrationRobustnessError):
        audit_parameter_sweep(
            kwargs["experiments"],  # type: ignore[arg-type]
            control_index=kwargs["control_index"],  # type: ignore[arg-type]
            family_name="family",
            parameter_name="x",
            metric_name="trade_count",
        )


def test_baseline_ecology_audit_is_aggregation_not_realism_certificate() -> None:
    first = audit_parameter_sweep(
        (
            _experiment("control", "1", (10, 10, 10)),
            _experiment("a", "2", (12, 12, 12)),
            _experiment("b", "3", (14, 14, 14)),
        ),
        control_index=0,
        family_name="family-a",
        parameter_name="x",
        metric_name="trade_count",
    )
    second = audit_parameter_sweep(
        (
            _experiment("control-2", "1", (10, 10, 10)),
            _experiment("c", "2", (8, 8, 8)),
            _experiment("d", "3", (7, 7, 7)),
        ),
        control_index=0,
        family_name="family-b",
        parameter_name="x",
        metric_name="trade_count",
    )

    audit = build_baseline_ecology_audit(
        (first, second),
        required_families=("family-a", "family-b"),
    )

    assert isinstance(audit, BaselineEcologyAudit)
    assert audit.complete
    assert audit.missing_families == ()
    assert audit.insufficient_families == ()
    assert audit.shared_seed_tuple == (11, 12, 13)
    assert audit.individual_interval_count == 4
    assert "not a certificate of empirical realism" in audit.interpretation_note


def test_baseline_ecology_audit_records_missing_insufficient_and_seed_warnings() -> None:
    enough = audit_parameter_sweep(
        (
            _experiment("control", "1", (10, 10, 10)),
            _experiment("a", "2", (12, 12, 12)),
            _experiment("b", "3", (14, 14, 14)),
        ),
        control_index=0,
        family_name="enough",
        parameter_name="x",
        metric_name="trade_count",
    )
    different_seeds = audit_parameter_sweep(
        (
            _experiment(
                "control-other",
                "1",
                (10, 10, 10),
                seeds=(21, 22, 23),
            ),
            _experiment(
                "only",
                "2",
                (11, 11, 11),
                seeds=(21, 22, 23),
            ),
        ),
        control_index=0,
        family_name="small",
        parameter_name="x",
        metric_name="trade_count",
    )

    audit = build_baseline_ecology_audit(
        (enough, different_seeds),
        required_families=("enough", "small", "missing"),
    )

    assert not audit.complete
    assert audit.missing_families == ("missing",)
    assert audit.insufficient_families == ("small",)
    assert audit.shared_seed_tuple is None
    assert len(audit.warnings) == 3


def test_baseline_ecology_audit_rejects_duplicate_family_names() -> None:
    family = audit_parameter_sweep(
        (
            _experiment("control", "1", (10, 10, 10)),
            _experiment("a", "2", (12, 12, 12)),
            _experiment("b", "3", (14, 14, 14)),
        ),
        control_index=0,
        family_name="duplicate",
        parameter_name="x",
        metric_name="trade_count",
    )

    with pytest.raises(CalibrationRobustnessError, match="unique"):
        build_baseline_ecology_audit(
            (family, family),
            required_families=("duplicate",),
        )
