"""Unit tests for precision-only flagship pilot artifacts."""

from dataclasses import replace
from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    PrecisionPilotPlan,
    PrecisionTarget,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)
from abmforge_finance.study.precision import (
    build_precision_pilot_artifact,
    verify_bundled_flagship_protocol,
    verify_precision_pilot_artifact,
    verify_precision_pilot_experiments,
)
from abmforge_finance.study.protocol import FlagshipStudyProtocol


def _small_protocol() -> FlagshipStudyProtocol:
    base = flagship_narrative_stability_protocol()
    return replace(
        base,
        protocol_id="flagship-narrative-stability-test",
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(2, 3, 4),
            targets=(
                PrecisionTarget("mean_thin_side_depletion", Decimal("10")),
                PrecisionTarget(
                    "mean_absolute_relative_dislocation",
                    Decimal("10"),
                ),
            ),
        ),
    )


def _experiments(
    protocol: FlagshipStudyProtocol,
) -> tuple[CalibrationExperimentResult, ...]:
    return run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=precision_pilot_seed_tuple(protocol),
    )


def test_official_runtime_protocol_matches_bundled_snapshot() -> None:
    verify_bundled_flagship_protocol(flagship_narrative_stability_protocol())


def test_precision_artifact_contains_widths_but_no_effect_estimates() -> None:
    protocol = _small_protocol()
    artifact = build_precision_pilot_artifact(
        protocol,
        _experiments(protocol),
        source_git_commit="a" * 40,
    )

    assert artifact.selected_seed_count == 2
    assert artifact.confirmatory_eligible
    assert artifact.decision_basis == "ci-half-width-only"
    assert not artifact.effect_estimates_included

    mapping = artifact.to_mapping()
    serialized = artifact.canonical_json
    assert "mean_difference" not in serialized
    assert "confidence_interval_lower" not in serialized
    assert "confidence_interval_upper" not in serialized
    assert "excludes_zero" not in serialized
    assert mapping["selected_seed_count"] == 2

    first = artifact.checkpoints[0]
    assert first.seed_count == 2
    assert tuple(item.metric_name for item in first.metrics) == (
        "mean_thin_side_depletion",
        "mean_absolute_relative_dislocation",
    )
    assert all(len(item.contrasts) == 4 for item in first.metrics)


def test_artifact_verification_rejects_protocol_fingerprint_tampering() -> None:
    protocol = _small_protocol()
    artifact = build_precision_pilot_artifact(
        protocol,
        _experiments(protocol),
        source_git_commit="b" * 40,
    )

    with pytest.raises(StudyProtocolError, match="fingerprint"):
        verify_precision_pilot_artifact(
            replace(artifact, protocol_fingerprint="0" * 64),
            protocol,
        )


def test_experiment_verification_rejects_wrong_treatment_order() -> None:
    protocol = _small_protocol()
    experiments = _experiments(protocol)

    with pytest.raises(StudyProtocolError, match="protocol order"):
        verify_precision_pilot_experiments(
            protocol,
            tuple(reversed(experiments)),
        )
