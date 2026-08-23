"""Validation tests for study protocol contracts."""

from dataclasses import replace
from decimal import Decimal

import pytest

from abmforge_finance.calibration import run_narrative_stability_homogeneity_sweep
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    FlagshipStudyProtocol,
    OutcomeRole,
    PrecisionPilotPlan,
    PrecisionPilotReport,
    PrecisionTarget,
    RobustnessRegime,
    StudyOutcome,
    apply_robustness_regime,
    confirmatory_seed_tuple,
    evaluate_precision_pilot,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
    study_seed_tuple,
)


def test_outcome_and_precision_targets_validate() -> None:
    with pytest.raises(StudyProtocolError):
        StudyOutcome("", OutcomeRole.PRIMARY)
    with pytest.raises(StudyProtocolError):
        PrecisionTarget("", Decimal("0.1"))
    with pytest.raises(StudyProtocolError):
        PrecisionTarget("metric", Decimal("0"))


def test_precision_candidates_and_targets_are_identified() -> None:
    target = PrecisionTarget("metric", Decimal("0.1"))

    with pytest.raises(StudyProtocolError, match="strictly increasing"):
        PrecisionPilotPlan((4, 2), (target,))
    with pytest.raises(StudyProtocolError, match="unique"):
        PrecisionPilotPlan((2, 4), (target, target))


def test_protocol_rejects_shared_seed_namespace_and_target_mismatch() -> None:
    protocol = flagship_narrative_stability_protocol()

    with pytest.raises(StudyProtocolError, match="distinct"):
        replace(
            protocol,
            confirmatory_seed_namespace=protocol.pilot_seed_namespace,
        )

    with pytest.raises(StudyProtocolError, match="primary outcome set"):
        replace(
            protocol,
            precision_plan=PrecisionPilotPlan(
                (10, 20),
                (PrecisionTarget("other", Decimal("0.1")),),
            ),
        )


def test_robustness_and_seed_contracts_reject_unknown_values() -> None:
    protocol = flagship_narrative_stability_protocol()

    with pytest.raises(StudyProtocolError, match="unsupported"):
        RobustnessRegime("bad", "unknown", "1")
    with pytest.raises(StudyProtocolError, match="unknown robustness"):
        apply_robustness_regime(protocol, "missing")
    with pytest.raises(StudyProtocolError, match="namespace"):
        study_seed_tuple(protocol, namespace="", count=2)


def test_precision_evaluator_requires_exact_treatment_grid() -> None:
    protocol = flagship_narrative_stability_protocol()

    with pytest.raises(StudyProtocolError, match="treatment grid"):
        evaluate_precision_pilot(protocol, ())


def test_extended_protocol_validation_paths() -> None:
    protocol = flagship_narrative_stability_protocol()

    with pytest.raises(StudyProtocolError, match="role must be"):
        StudyOutcome(
            "metric",
            "primary",  # type: ignore[arg-type]
        )

    with pytest.raises(StudyProtocolError, match="candidate_seed_counts"):
        PrecisionPilotPlan(
            (),
            (PrecisionTarget("metric", Decimal("0.1")),),
        )

    with pytest.raises(StudyProtocolError, match="integers >= 2"):
        PrecisionPilotPlan(
            (1, 2),
            (PrecisionTarget("metric", Decimal("0.1")),),
        )

    with pytest.raises(StudyProtocolError, match="confidence_level"):
        PrecisionPilotPlan(
            (2, 4),
            (PrecisionTarget("metric", Decimal("0.1")),),
            confidence_level=Decimal("1"),
        )

    with pytest.raises(StudyProtocolError, match="regime_id"):
        RobustnessRegime("", "noise_trader_count", "2")

    with pytest.raises(StudyProtocolError, match="parameter_value"):
        RobustnessRegime("bad", "noise_trader_count", "")

    with pytest.raises(StudyProtocolError, match="benchmark_config"):
        replace(
            protocol,
            benchmark_config=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(StudyProtocolError, match="control_homogeneity"):
        replace(
            protocol,
            control_homogeneity=Decimal("0.33"),
        )

    with pytest.raises(StudyProtocolError, match="at least one primary"):
        replace(
            protocol,
            outcomes=tuple(replace(item, role=OutcomeRole.SECONDARY) for item in protocol.outcomes),
        )

    with pytest.raises(StudyProtocolError, match="familywise_alpha"):
        replace(
            protocol,
            familywise_alpha=Decimal("0"),
        )

    with pytest.raises(StudyProtocolError, match="regime IDs"):
        replace(
            protocol,
            robustness_regimes=(
                protocol.robustness_regimes[0],
                protocol.robustness_regimes[0],
            ),
        )


def test_invalid_direction_schedule_regime_is_rejected_at_protocol_validation() -> None:
    protocol = flagship_narrative_stability_protocol()

    with pytest.raises(StudyProtocolError, match="invalid direction_schedule"):
        replace(
            protocol,
            robustness_regimes=(
                RobustnessRegime(
                    "bad-schedule",
                    "direction_schedule",
                    "bullish,sideways",
                ),
            ),
        )


def test_apply_robustness_rejects_wrong_protocol_type() -> None:
    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        apply_robustness_regime(
            object(),  # type: ignore[arg-type]
            "liquidity-low",
        )


def test_seed_helpers_validate_protocol_type_namespace_and_count() -> None:
    protocol = flagship_narrative_stability_protocol()

    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        study_seed_tuple(
            object(),  # type: ignore[arg-type]
            namespace="x",
            count=2,
        )

    with pytest.raises(StudyProtocolError, match="namespace"):
        study_seed_tuple(protocol, namespace="", count=2)

    with pytest.raises(StudyProtocolError, match="positive integer"):
        study_seed_tuple(
            protocol,
            namespace="x",
            count=True,
        )

    with pytest.raises(StudyProtocolError, match="prespecified candidate"):
        confirmatory_seed_tuple(protocol, 3)


def test_precision_evaluator_rejects_wrong_protocol_type() -> None:
    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        evaluate_precision_pilot(
            object(),  # type: ignore[arg-type]
            (),
        )


def _small_precision_protocol() -> FlagshipStudyProtocol:
    protocol = flagship_narrative_stability_protocol()
    return replace(
        protocol,
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(2, 3),
            targets=(
                PrecisionTarget(
                    "mean_thin_side_depletion",
                    Decimal("10"),
                ),
                PrecisionTarget(
                    "mean_absolute_relative_dislocation",
                    Decimal("10"),
                ),
            ),
        ),
    )


def test_precision_evaluator_rejects_wrong_seed_tuple() -> None:
    protocol = _small_precision_protocol()
    wrong_seeds = (111, 222, 333)

    experiments = run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=wrong_seeds,
    )

    assert wrong_seeds != precision_pilot_seed_tuple(protocol)

    with pytest.raises(StudyProtocolError, match="full pilot seed tuple"):
        evaluate_precision_pilot(protocol, experiments)


def test_precision_evaluator_rejects_wrong_homogeneity_order() -> None:
    protocol = _small_precision_protocol()
    seeds = precision_pilot_seed_tuple(protocol)

    experiments = run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=seeds,
    )

    with pytest.raises(StudyProtocolError, match="protocol order"):
        evaluate_precision_pilot(
            protocol,
            tuple(reversed(experiments)),
        )


def test_precision_report_ready_flag_can_represent_failure() -> None:
    report = PrecisionPilotReport(
        protocol_fingerprint="abc",
        checkpoints=(),
        selected_seed_count=None,
    )

    assert not report.ready_for_confirmatory_run
