"""Extended validation paths for the Phase 10E precision-pilot artifact."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    FlagshipStudyProtocol,
    PrecisionPilotPlan,
    PrecisionTarget,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)
from abmforge_finance.study import precision as precision_module
from abmforge_finance.study.precision import (
    PrecisionContrastWidth,
    PrecisionPilotArtifact,
    build_precision_pilot_artifact,
    verify_bundled_flagship_protocol,
    verify_precision_pilot_artifact,
    verify_precision_pilot_experiments,
    write_precision_pilot_artifact,
)


def _protocol() -> FlagshipStudyProtocol:
    return replace(
        flagship_narrative_stability_protocol(),
        protocol_id="precision-validation",
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


def _experiments(
    protocol: FlagshipStudyProtocol,
) -> tuple[CalibrationExperimentResult, ...]:
    return run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=precision_pilot_seed_tuple(protocol),
    )


def _artifact(
    protocol: FlagshipStudyProtocol,
) -> PrecisionPilotArtifact:
    return build_precision_pilot_artifact(
        protocol,
        _experiments(protocol),
        source_git_commit="e" * 40,
    )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        (
            {"artifact_schema_version": "unknown-schema"},
            "schema version",
        ),
        (
            {"source_git_commit": "ABC"},
            "Git SHA",
        ),
        (
            {"decision_basis": "effect-sign"},
            "decision basis",
        ),
        (
            {"effect_estimates_included": True},
            "must not include",
        ),
        (
            {
                "selected_seed_count": None,
                "confirmatory_eligible": True,
            },
            "eligibility",
        ),
    ],
)
def test_precision_artifact_constructor_rejects_invalid_contract(
    changes: dict[str, object],
    match: str,
) -> None:
    protocol = _protocol()
    artifact = _artifact(protocol)

    with pytest.raises(StudyProtocolError, match=match):
        replace(artifact, **changes)  # type: ignore[arg-type]


def test_experiment_verifier_rejects_invalid_member_and_seed_tampering() -> None:
    protocol = _protocol()
    experiments = _experiments(protocol)

    with pytest.raises(StudyProtocolError, match="CalibrationExperimentResult"):
        verify_precision_pilot_experiments(
            protocol,
            (object(),) * len(protocol.homogeneities),  # type: ignore[arg-type]
        )

    first = experiments[0]
    first_run = first.runs[0]
    tampered_run = replace(
        first_run,
        spec=replace(first_run.spec, seed=first_run.spec.seed + 1),
    )
    tampered_first = replace(
        first,
        runs=(tampered_run, *first.runs[1:]),
    )

    with pytest.raises(StudyProtocolError, match="pilot seed tuple"):
        verify_precision_pilot_experiments(
            protocol,
            (tampered_first, *experiments[1:]),
        )


@pytest.mark.parametrize(
    ("field", "replacement", "match"),
    [
        ("protocol_id", "other-protocol", "protocol_id"),
        ("protocol_version", "9.9.9", "protocol_version"),
        ("pilot_seed_namespace", "other", "seed namespace"),
        ("pilot_seed_count", 999, "seed count"),
        ("pilot_seed_fingerprint", "0" * 64, "seed fingerprint"),
        ("candidate_seed_counts", (2, 4), "candidate seed counts"),
    ],
)
def test_artifact_verifier_rejects_provenance_tampering(
    field: str,
    replacement: object,
    match: str,
) -> None:
    protocol = _protocol()
    artifact = _artifact(protocol)

    with pytest.raises(StudyProtocolError, match=match):
        verify_precision_pilot_artifact(
            replace(artifact, **{field: replacement}),  # type: ignore[arg-type]
            protocol,
        )


def test_artifact_verifier_rejects_checkpoint_seed_count_tampering() -> None:
    protocol = _protocol()
    artifact = _artifact(protocol)
    first = artifact.checkpoints[0]
    tampered = replace(
        artifact,
        checkpoints=(
            replace(first, seed_count=99),
            *artifact.checkpoints[1:],
        ),
    )

    with pytest.raises(StudyProtocolError, match="checkpoints"):
        verify_precision_pilot_artifact(tampered, protocol)


def test_artifact_verifier_rejects_metric_order_and_target_tampering() -> None:
    protocol = _protocol()
    artifact = _artifact(protocol)
    checkpoint = artifact.checkpoints[0]

    wrong_order = replace(
        checkpoint,
        metrics=tuple(reversed(checkpoint.metrics)),
    )
    with pytest.raises(StudyProtocolError, match="metric order"):
        verify_precision_pilot_artifact(
            replace(
                artifact,
                checkpoints=(wrong_order, *artifact.checkpoints[1:]),
            ),
            protocol,
        )

    first_metric = checkpoint.metrics[0]
    wrong_target = replace(
        first_metric,
        target_half_width=Decimal("999"),
    )
    with pytest.raises(StudyProtocolError, match="precision target"):
        verify_precision_pilot_artifact(
            replace(
                artifact,
                checkpoints=(
                    replace(
                        checkpoint,
                        metrics=(wrong_target, *checkpoint.metrics[1:]),
                    ),
                    *artifact.checkpoints[1:],
                ),
            ),
            protocol,
        )


def test_artifact_verifier_rejects_contrast_order_and_maximum_tampering() -> None:
    protocol = _protocol()
    artifact = _artifact(protocol)
    checkpoint = artifact.checkpoints[0]
    metric = checkpoint.metrics[0]

    reversed_contrasts = replace(
        metric,
        contrasts=tuple(reversed(metric.contrasts)),
    )
    with pytest.raises(StudyProtocolError, match="contrast order"):
        verify_precision_pilot_artifact(
            replace(
                artifact,
                checkpoints=(
                    replace(
                        checkpoint,
                        metrics=(
                            reversed_contrasts,
                            *checkpoint.metrics[1:],
                        ),
                    ),
                    *artifact.checkpoints[1:],
                ),
            ),
            protocol,
        )

    wrong_max = replace(
        metric,
        maximum_half_width=metric.maximum_half_width + 1.0,
    )
    with pytest.raises(StudyProtocolError, match="maximum half-width"):
        verify_precision_pilot_artifact(
            replace(
                artifact,
                checkpoints=(
                    replace(
                        checkpoint,
                        metrics=(wrong_max, *checkpoint.metrics[1:]),
                    ),
                    *artifact.checkpoints[1:],
                ),
            ),
            protocol,
        )


def test_artifact_verifier_rejects_metric_and_checkpoint_decision_tampering() -> None:
    protocol = _protocol()
    artifact = _artifact(protocol)
    checkpoint = artifact.checkpoints[0]
    metric = checkpoint.metrics[0]

    wrong_metric_decision = replace(
        metric,
        criterion_met=not metric.criterion_met,
    )
    with pytest.raises(StudyProtocolError, match="metric precision decision"):
        verify_precision_pilot_artifact(
            replace(
                artifact,
                checkpoints=(
                    replace(
                        checkpoint,
                        metrics=(
                            wrong_metric_decision,
                            *checkpoint.metrics[1:],
                        ),
                    ),
                    *artifact.checkpoints[1:],
                ),
            ),
            protocol,
        )

    wrong_checkpoint_decision = replace(
        checkpoint,
        all_targets_met=not checkpoint.all_targets_met,
    )
    with pytest.raises(StudyProtocolError, match="checkpoint precision decision"):
        verify_precision_pilot_artifact(
            replace(
                artifact,
                checkpoints=(
                    wrong_checkpoint_decision,
                    *artifact.checkpoints[1:],
                ),
            ),
            protocol,
        )


def test_artifact_serialization_helpers_reject_invalid_widths() -> None:
    contrast = PrecisionContrastWidth(
        treatment_homogeneity=Decimal("0.25"),
        ci_half_width=float("nan"),
    )

    with pytest.raises(StudyProtocolError, match="half-width"):
        contrast.to_mapping()


def test_writer_rejects_wrong_type_and_existing_temporary_file(
    tmp_path: Path,
) -> None:
    protocol = _protocol()
    artifact = _artifact(protocol)
    target = tmp_path / "pilot.json"

    with pytest.raises(TypeError, match="PrecisionPilotArtifact"):
        write_precision_pilot_artifact(
            object(),  # type: ignore[arg-type]
            target,
        )

    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text("occupied", encoding="utf-8")

    with pytest.raises(StudyProtocolError, match="temporary artifact"):
        write_precision_pilot_artifact(artifact, target)


def test_bundled_protocol_verifier_detects_snapshot_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = flagship_narrative_stability_protocol()
    mapping = protocol.to_mapping()
    tampered = dict(mapping)
    tampered["protocol_version"] = "tampered"

    monkeypatch.setattr(
        precision_module,
        "bundled_flagship_protocol_mapping",
        lambda: tampered,
    )

    with pytest.raises(StudyProtocolError, match="bundled JSON"):
        verify_bundled_flagship_protocol(protocol)


def test_private_contrast_homogeneity_validation_paths() -> None:
    with pytest.raises(StudyProtocolError, match="treatment scenario"):
        precision_module._contrast_homogeneity(object())

    missing = SimpleNamespace(treatment_scenario=SimpleNamespace(parameters=(("other", "1"),)))
    with pytest.raises(StudyProtocolError, match="expose homogeneity"):
        precision_module._contrast_homogeneity(missing)

    nonfinite = SimpleNamespace(
        treatment_scenario=SimpleNamespace(parameters=(("homogeneity", "NaN"),))
    )
    with pytest.raises(StudyProtocolError, match="must be finite"):
        precision_module._contrast_homogeneity(nonfinite)


def test_build_artifact_rejects_wrong_protocol_type() -> None:
    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        build_precision_pilot_artifact(
            object(),  # type: ignore[arg-type]
            (),
            source_git_commit="f" * 40,
        )


def test_artifact_verifier_rejects_wrong_public_argument_types() -> None:
    protocol = _protocol()
    artifact = _artifact(protocol)

    with pytest.raises(TypeError, match="PrecisionPilotArtifact"):
        verify_precision_pilot_artifact(
            object(),  # type: ignore[arg-type]
            protocol,
        )

    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        verify_precision_pilot_artifact(
            artifact,
            object(),  # type: ignore[arg-type]
        )
