"""Extended Phase 10F validation coverage.

These tests exercise confirmatory provenance and tamper-detection branches without
executing the official 50-run confirmatory study.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    FlagshipStudyProtocol,
    OutcomeRole,
    PrecisionPilotPlan,
    PrecisionTarget,
    confirmatory_seed_tuple,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)
from abmforge_finance.study import confirmatory as confirmatory_module
from abmforge_finance.study.confirmatory import (
    ConfirmatoryArtifact,
    PrecisionPilotDecision,
    build_confirmatory_artifact,
    load_precision_pilot_decision,
    verify_confirmatory_artifact,
    verify_confirmatory_experiments,
    write_confirmatory_artifact,
)


def _protocol() -> FlagshipStudyProtocol:
    return replace(
        flagship_narrative_stability_protocol(),
        protocol_id="confirmatory-extended-validation",
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(2,),
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


def _decision(protocol: FlagshipStudyProtocol) -> PrecisionPilotDecision:
    pilot_seeds = precision_pilot_seed_tuple(protocol)
    return PrecisionPilotDecision(
        artifact_sha256="a" * 64,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_fingerprint=protocol.fingerprint,
        precision_source_git_commit="b" * 40,
        pilot_seed_namespace=protocol.pilot_seed_namespace,
        pilot_seed_count=len(pilot_seeds),
        pilot_seed_fingerprint="c" * 64,
        selected_seed_count=2,
    )


def _experiments(
    protocol: FlagshipStudyProtocol,
) -> tuple[CalibrationExperimentResult, ...]:
    return run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=confirmatory_seed_tuple(protocol, 2),
    )


def _artifact(
    protocol: FlagshipStudyProtocol,
    decision: PrecisionPilotDecision,
) -> ConfirmatoryArtifact:
    return build_confirmatory_artifact(
        protocol,
        decision,
        _experiments(protocol),
        source_git_commit="d" * 40,
    )


def _official_mapping() -> dict[str, object]:
    path = Path("artifacts/flagship/precision-pilot.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_mapping(
    tmp_path: Path,
    mapping: object,
) -> tuple[Path, str]:
    path = tmp_path / "precision.json"
    payload = (
        json.dumps(
            mapping,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (
            {"artifact_sha256": "bad"},
            "SHA-256",
        ),
        (
            {"precision_source_git_commit": "bad"},
            "Git commit",
        ),
        (
            {"selected_seed_count": 1},
            "selected_seed_count",
        ),
        (
            {"selected_seed_count": True},
            "selected_seed_count",
        ),
    ],
)
def test_precision_decision_constructor_rejects_invalid_contract(
    kwargs: dict[str, object],
    match: str,
) -> None:
    protocol = _protocol()
    base = _decision(protocol)

    with pytest.raises(StudyProtocolError, match=match):
        replace(base, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_confirmatory_float_serializer_rejects_nonfinite(
    value: float,
) -> None:
    with pytest.raises(StudyProtocolError, match="finite"):
        confirmatory_module._float_text(value)


@pytest.mark.parametrize(
    "value",
    [-0.1, 1.1, float("nan"), float("inf")],
)
def test_probability_serializer_rejects_invalid_values(
    value: float,
) -> None:
    with pytest.raises(StudyProtocolError, match=r"\[0, 1\]"):
        confirmatory_module._probability_text(value)


def test_precision_loader_rejects_wrong_public_argument_types() -> None:
    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        load_precision_pilot_decision(
            "unused.json",
            object(),  # type: ignore[arg-type]
        )

    with pytest.raises(StudyProtocolError, match="expected precision"):
        load_precision_pilot_decision(
            "unused.json",
            flagship_narrative_stability_protocol(),
            expected_sha256="bad",
        )


@pytest.mark.parametrize(
    ("field", "replacement", "match"),
    [
        (
            "artifact_schema_version",
            "wrong",
            "artifact_schema_version",
        ),
        ("protocol_id", "wrong", "protocol_id"),
        ("protocol_version", "wrong", "protocol_version"),
        ("protocol_fingerprint", "0" * 64, "protocol_fingerprint"),
        ("pilot_seed_namespace", "wrong", "pilot_seed_namespace"),
        ("decision_basis", "peek-at-effects", "decision_basis"),
        ("effect_estimates_included", True, "effect_estimates_included"),
        ("confirmatory_eligible", False, "confirmatory_eligible"),
    ],
)
def test_precision_loader_rejects_contract_field_tampering(
    tmp_path: Path,
    field: str,
    replacement: object,
    match: str,
) -> None:
    mapping = _official_mapping()
    mapping[field] = replacement
    path, digest = _write_mapping(tmp_path, mapping)

    with pytest.raises(StudyProtocolError, match=match):
        load_precision_pilot_decision(
            path,
            flagship_narrative_stability_protocol(),
            expected_sha256=digest,
        )


def test_precision_loader_rejects_nonobject_json(
    tmp_path: Path,
) -> None:
    path, digest = _write_mapping(tmp_path, [1, 2, 3])

    with pytest.raises(StudyProtocolError, match="JSON must be an object"):
        load_precision_pilot_decision(
            path,
            flagship_narrative_stability_protocol(),
            expected_sha256=digest,
        )


def test_precision_loader_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "precision.json"
    payload = b"{not-json\n"
    path.write_bytes(payload)

    with pytest.raises(StudyProtocolError, match="valid UTF-8 JSON"):
        load_precision_pilot_decision(
            path,
            flagship_narrative_stability_protocol(),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("candidate_counts", "candidate seed counts"),
        ("pilot_count", "pilot seed count"),
        ("pilot_fingerprint", "pilot seed fingerprint"),
        ("source_commit", "source_git_commit"),
        ("selected", "selected_seed_count"),
        ("checkpoints_type", "checkpoints must be a list"),
        ("checkpoint_member", "must contain objects"),
        ("checkpoint_seed", "seed_count is invalid"),
        ("checkpoint_met", "all_targets_met is invalid"),
        ("checkpoint_order", "checkpoint order"),
        ("smallest_n", "smallest-n rule"),
    ],
)
def test_precision_loader_rejects_structural_tampering(
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    mapping = _official_mapping()

    if mutation == "candidate_counts":
        mapping["candidate_seed_counts"] = [10, 20]
    elif mutation == "pilot_count":
        mapping["pilot_seed_count"] = 159
    elif mutation == "pilot_fingerprint":
        mapping["pilot_seed_fingerprint"] = "0" * 64
    elif mutation == "source_commit":
        mapping["source_git_commit"] = "bad"
    elif mutation == "selected":
        mapping["selected_seed_count"] = 11
    elif mutation == "checkpoints_type":
        mapping["checkpoints"] = {}
    elif mutation == "checkpoint_member":
        mapping["checkpoints"] = ["bad"]
    elif mutation == "checkpoint_seed":
        checkpoints = list(
            cast(
                list[dict[str, object]],
                mapping["checkpoints"],
            )
        )
        first = dict(checkpoints[0])
        first["seed_count"] = True
        checkpoints[0] = first
        mapping["checkpoints"] = checkpoints
    elif mutation == "checkpoint_met":
        checkpoints = list(
            cast(
                list[dict[str, object]],
                mapping["checkpoints"],
            )
        )
        first = dict(checkpoints[0])
        first["all_targets_met"] = "yes"
        checkpoints[0] = first
        mapping["checkpoints"] = checkpoints
    elif mutation == "checkpoint_order":
        checkpoints = list(
            cast(
                list[dict[str, object]],
                mapping["checkpoints"],
            )
        )
        mapping["checkpoints"] = list(reversed(checkpoints))
    elif mutation == "smallest_n":
        mapping["selected_seed_count"] = 20
    else:  # pragma: no cover - parametrization exhausts this
        raise AssertionError(mutation)

    path, digest = _write_mapping(tmp_path, mapping)
    with pytest.raises(StudyProtocolError, match=match):
        load_precision_pilot_decision(
            path,
            flagship_narrative_stability_protocol(),
            expected_sha256=digest,
        )


def test_confirmatory_experiment_verifier_rejects_public_argument_errors() -> None:
    protocol = _protocol()
    decision = _decision(protocol)

    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        verify_confirmatory_experiments(
            object(),  # type: ignore[arg-type]
            decision,
            (),
        )

    with pytest.raises(TypeError, match="PrecisionPilotDecision"):
        verify_confirmatory_experiments(
            protocol,
            object(),  # type: ignore[arg-type]
            (),
        )

    with pytest.raises(StudyProtocolError, match="protocol fingerprint"):
        verify_confirmatory_experiments(
            protocol,
            replace(decision, protocol_fingerprint="0" * 64),
            (),
        )


def test_confirmatory_experiment_verifier_rejects_shape_and_member_errors() -> None:
    protocol = _protocol()
    decision = _decision(protocol)

    with pytest.raises(StudyProtocolError, match="treatment grid"):
        verify_confirmatory_experiments(protocol, decision, ())

    with pytest.raises(
        StudyProtocolError,
        match="CalibrationExperimentResult",
    ):
        verify_confirmatory_experiments(
            protocol,
            decision,
            (object(),) * len(protocol.homogeneities),  # type: ignore[arg-type]
        )


def test_confirmatory_experiment_verifier_detects_seed_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    confirmatory = confirmatory_seed_tuple(protocol, 2)

    monkeypatch.setattr(
        confirmatory_module,
        "precision_pilot_seed_tuple",
        lambda _: confirmatory,
    )

    with pytest.raises(StudyProtocolError, match="overlap"):
        verify_confirmatory_experiments(
            protocol,
            decision,
            _experiments(protocol),
        )


def test_confirmatory_experiment_homogeneity_validation_paths() -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    experiments = _experiments(protocol)
    first = experiments[0]

    missing = replace(
        first,
        scenario=replace(
            first.scenario,
            parameters=tuple(
                (key, value) for key, value in first.scenario.parameters if key != "homogeneity"
            ),
        ),
    )
    with pytest.raises(StudyProtocolError, match="expose homogeneity"):
        verify_confirmatory_experiments(
            protocol,
            decision,
            (missing, *experiments[1:]),
        )

    nonfinite = replace(
        first,
        scenario=replace(
            first.scenario,
            parameters=tuple(
                (
                    key,
                    "NaN" if key == "homogeneity" else value,
                )
                for key, value in first.scenario.parameters
            ),
        ),
    )
    with pytest.raises(StudyProtocolError, match="must be finite"):
        verify_confirmatory_experiments(
            protocol,
            decision,
            (nonfinite, *experiments[1:]),
        )


def test_confirmatory_experiment_verifier_rejects_non_h_scenario_tampering() -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    experiments = _experiments(protocol)
    first = experiments[0]

    tampered = replace(
        first,
        scenario=replace(
            first.scenario,
            parameters=tuple(
                (
                    key,
                    "999" if key == "noise_activity_bps" else value,
                )
                for key, value in first.scenario.parameters
            ),
        ),
    )

    with pytest.raises(StudyProtocolError, match="exactly match protocol"):
        verify_confirmatory_experiments(
            protocol,
            decision,
            (tampered, *experiments[1:]),
        )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        (
            {"artifact_schema_version": "wrong"},
            "schema version",
        ),
        (
            {"source_git_commit": "bad"},
            "source_git_commit",
        ),
        (
            {"precision_artifact_sha256": "bad"},
            "precision_artifact_sha256",
        ),
        (
            {"precision_source_git_commit": "bad"},
            "precision_source_git_commit",
        ),
        (
            {"interval_scope": "wrong"},
            "interval scope",
        ),
        (
            {"pilot_seed_overlap_count": 1},
            "pilot seed overlap",
        ),
    ],
)
def test_confirmatory_artifact_constructor_rejects_invalid_contract(
    changes: dict[str, object],
    match: str,
) -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = _artifact(protocol, decision)

    with pytest.raises(StudyProtocolError, match=match):
        replace(artifact, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "replacement", "match"),
    [
        ("protocol_id", "wrong", "protocol_id"),
        ("protocol_version", "wrong", "protocol_version"),
        ("protocol_fingerprint", "0" * 64, "protocol fingerprint"),
        ("precision_artifact_sha256", "f" * 64, "artifact SHA"),
        (
            "precision_source_git_commit",
            "e" * 40,
            "source commit",
        ),
        ("selected_seed_count", 3, "selected seed count"),
        ("confirmatory_seed_namespace", "wrong", "seed namespace"),
        ("confirmatory_seed_count", 999, "seed count"),
        ("confirmatory_seed_fingerprint", "0" * 64, "seed fingerprint"),
        (
            "nominal_confidence_level",
            0.90,
            "nominal confidence",
        ),
        ("multiplicity_method", "none", "multiplicity method"),
        ("familywise_alpha", 0.10, "familywise alpha"),
        ("multiplicity_scope", "wrong", "multiplicity scope"),
        (
            "primary_hypothesis_count",
            7,
            "primary hypothesis count",
        ),
    ],
)
def test_confirmatory_artifact_verifier_rejects_provenance_tampering(
    field: str,
    replacement: object,
    match: str,
) -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = _artifact(protocol, decision)

    with pytest.raises(StudyProtocolError, match=match):
        verify_confirmatory_artifact(
            replace(artifact, **{field: replacement}),  # type: ignore[arg-type]
            protocol,
            decision,
        )


def test_confirmatory_artifact_verifier_rejects_public_argument_types() -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = _artifact(protocol, decision)

    with pytest.raises(TypeError, match="ConfirmatoryArtifact"):
        verify_confirmatory_artifact(
            object(),  # type: ignore[arg-type]
            protocol,
            decision,
        )
    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        verify_confirmatory_artifact(
            artifact,
            object(),  # type: ignore[arg-type]
            decision,
        )
    with pytest.raises(TypeError, match="PrecisionPilotDecision"):
        verify_confirmatory_artifact(
            artifact,
            protocol,
            object(),  # type: ignore[arg-type]
        )


def test_confirmatory_artifact_verifier_rejects_outcome_and_pair_tampering() -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = _artifact(protocol, decision)

    with pytest.raises(StudyProtocolError, match="outcome order or role"):
        verify_confirmatory_artifact(
            replace(
                artifact,
                outcomes=tuple(reversed(artifact.outcomes)),
            ),
            protocol,
            decision,
        )

    first = artifact.outcomes[0]
    with pytest.raises(StudyProtocolError, match="treatment contrast order"):
        verify_confirmatory_artifact(
            replace(
                artifact,
                outcomes=(
                    replace(
                        first,
                        contrasts=tuple(reversed(first.contrasts)),
                    ),
                    *artifact.outcomes[1:],
                ),
            ),
            protocol,
            decision,
        )

    first_contrast = first.contrasts[0]
    with pytest.raises(StudyProtocolError, match="pair count"):
        verify_confirmatory_artifact(
            replace(
                artifact,
                outcomes=(
                    replace(
                        first,
                        contrasts=(
                            replace(
                                first_contrast,
                                pair_count=999,
                            ),
                            *first.contrasts[1:],
                        ),
                    ),
                    *artifact.outcomes[1:],
                ),
            ),
            protocol,
            decision,
        )


def test_confirmatory_artifact_verifier_rejects_primary_field_tampering() -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = _artifact(protocol, decision)
    primary_index = next(
        index
        for index, outcome in enumerate(artifact.outcomes)
        if outcome.role is OutcomeRole.PRIMARY
    )
    primary = artifact.outcomes[primary_index]
    contrast = primary.contrasts[0]

    outcomes = list(artifact.outcomes)
    outcomes[primary_index] = replace(
        primary,
        contrasts=(
            replace(contrast, hypothesis_id="wrong"),
            *primary.contrasts[1:],
        ),
    )
    with pytest.raises(StudyProtocolError, match="hypothesis ID"):
        verify_confirmatory_artifact(
            replace(artifact, outcomes=tuple(outcomes)),
            protocol,
            decision,
        )

    outcomes = list(artifact.outcomes)
    outcomes[primary_index] = replace(
        primary,
        contrasts=(
            replace(contrast, raw_p_value=None),
            *primary.contrasts[1:],
        ),
    )
    with pytest.raises(StudyProtocolError, match="require Holm"):
        verify_confirmatory_artifact(
            replace(artifact, outcomes=tuple(outcomes)),
            protocol,
            decision,
        )

    assert contrast.holm_reject is not None
    outcomes = list(artifact.outcomes)
    outcomes[primary_index] = replace(
        primary,
        contrasts=(
            replace(
                contrast,
                holm_reject=not contrast.holm_reject,
            ),
            *primary.contrasts[1:],
        ),
    )
    with pytest.raises(StudyProtocolError, match="rejection decision"):
        verify_confirmatory_artifact(
            replace(artifact, outcomes=tuple(outcomes)),
            protocol,
            decision,
        )


def test_confirmatory_serialization_rejects_nonfinite_effect_value() -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = _artifact(protocol, decision)
    first = artifact.outcomes[0]
    contrast = first.contrasts[0]
    tampered = replace(
        contrast,
        mean_difference=float("nan"),
    )

    with pytest.raises(StudyProtocolError, match="finite"):
        tampered.to_mapping()


def test_confirmatory_writer_rejects_wrong_type_and_temp_collision(
    tmp_path: Path,
) -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = _artifact(protocol, decision)
    target = tmp_path / "confirmatory.json"

    with pytest.raises(TypeError, match="ConfirmatoryArtifact"):
        write_confirmatory_artifact(
            object(),  # type: ignore[arg-type]
            target,
        )

    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text("occupied", encoding="utf-8")
    with pytest.raises(StudyProtocolError, match="temporary artifact"):
        write_confirmatory_artifact(artifact, target)
