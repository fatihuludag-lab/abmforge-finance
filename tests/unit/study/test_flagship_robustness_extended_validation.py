"""Extended validation coverage for the Phase 10G robustness layer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    PairedTreatmentContrast,
    infer_narrative_stability_sweep,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    FlagshipStudyProtocol,
    OutcomeRole,
    PrecisionPilotPlan,
    PrecisionTarget,
    apply_robustness_regime,
    flagship_narrative_stability_protocol,
)
from abmforge_finance.study import robustness as robustness_module
from abmforge_finance.study.robustness import (
    ConfirmatoryRobustnessAnchor,
    RobustnessAuditArtifact,
    RobustnessRegimeExperiments,
    build_robustness_audit_artifact,
    load_confirmatory_robustness_anchor,
    robustness_seed_tuple,
    verify_robustness_experiments,
    write_robustness_audit_artifact,
)


def _protocol() -> FlagshipStudyProtocol:
    base = flagship_narrative_stability_protocol()
    return replace(
        base,
        protocol_id="robustness-extended-validation",
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
        robustness_regimes=base.robustness_regimes[:2],
    )


def _anchor(
    protocol: FlagshipStudyProtocol,
) -> ConfirmatoryRobustnessAnchor:
    treatments = protocol.homogeneities[1:]
    return ConfirmatoryRobustnessAnchor(
        artifact_sha256="a" * 64,
        source_git_commit="b" * 40,
        protocol_fingerprint=protocol.fingerprint,
        precision_artifact_sha256="c" * 64,
        selected_seed_count=2,
        confirmatory_seed_fingerprint="d" * 64,
        primary_effects=tuple(
            (
                metric,
                tuple((h, 0.1 * float(index + 1)) for index, h in enumerate(treatments)),
            )
            for metric in protocol.primary_metric_names
        ),
    )


def _regimes(
    protocol: FlagshipStudyProtocol,
) -> tuple[RobustnessRegimeExperiments, ...]:
    seeds = robustness_seed_tuple(protocol, 2)
    return tuple(
        RobustnessRegimeExperiments(
            regime_id=regime.regime_id,
            experiments=run_narrative_stability_homogeneity_sweep(
                apply_robustness_regime(
                    protocol,
                    regime.regime_id,
                ),
                homogeneities=protocol.homogeneities,
                seeds=seeds,
            ),
        )
        for regime in protocol.robustness_regimes
    )


def _mapping() -> dict[str, Any]:
    value = json.loads(Path("artifacts/flagship/confirmatory.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _write(
    tmp_path: Path,
    mapping: object,
) -> tuple[Path, str]:
    path = tmp_path / "confirmatory.json"
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


def _minimal_artifact() -> RobustnessAuditArtifact:
    return RobustnessAuditArtifact(
        artifact_schema_version="robustness-audit-artifact-v1",
        protocol_id="p",
        protocol_version="1",
        protocol_fingerprint="f" * 64,
        source_git_commit="a" * 40,
        confirmatory_artifact_sha256="b" * 64,
        confirmatory_source_git_commit="c" * 40,
        selected_seed_count=2,
        robustness_seed_namespace="robustness-v1",
        robustness_seed_count=2,
        robustness_seed_fingerprint="d" * 64,
        pilot_seed_overlap_count=0,
        confirmatory_seed_overlap_count=0,
        confidence_level=0.95,
        interval_scope="nominal-per-contrast-not-familywise",
        inference_scope=("estimation-only-no-additional-multiplicity-family"),
        regimes=(),
    )


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_numeric_helpers_reject_nonfinite(value: float) -> None:
    with pytest.raises(StudyProtocolError, match="finite"):
        robustness_module._float_text(value)
    with pytest.raises(StudyProtocolError, match="finite"):
        robustness_module._sign(value)


def test_anchor_loader_rejects_public_argument_errors() -> None:
    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        load_confirmatory_robustness_anchor(
            "unused.json",
            object(),  # type: ignore[arg-type]
        )

    with pytest.raises(StudyProtocolError, match="expected confirmatory"):
        load_confirmatory_robustness_anchor(
            "unused.json",
            flagship_narrative_stability_protocol(),
            expected_sha256="bad",
        )


def test_anchor_loader_rejects_invalid_json_and_nonobject(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid.json"
    payload = b"{bad-json\n"
    invalid.write_bytes(payload)
    with pytest.raises(StudyProtocolError, match="valid UTF-8 JSON"):
        load_confirmatory_robustness_anchor(
            invalid,
            flagship_narrative_stability_protocol(),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )

    path, digest = _write(tmp_path, [1, 2, 3])
    with pytest.raises(StudyProtocolError, match="JSON must be an object"):
        load_confirmatory_robustness_anchor(
            path,
            flagship_narrative_stability_protocol(),
            expected_sha256=digest,
        )


@pytest.mark.parametrize(
    ("field", "replacement", "match"),
    [
        ("artifact_schema_version", "wrong", "artifact_schema_version"),
        ("protocol_id", "wrong", "protocol_id"),
        ("protocol_version", "wrong", "protocol_version"),
        ("protocol_fingerprint", "0" * 64, "protocol_fingerprint"),
        ("confirmatory_seed_namespace", "wrong", "confirmatory_seed_namespace"),
        ("pilot_seed_overlap_count", 1, "pilot_seed_overlap_count"),
        ("source_git_commit", "bad", "source_git_commit"),
        ("precision_artifact_sha256", "bad", "precision artifact SHA-256"),
        ("selected_seed_count", 11, "selected_seed_count"),
        ("confirmatory_seed_count", 9, "seed count"),
        ("confirmatory_seed_fingerprint", "0" * 64, "seed fingerprint"),
    ],
)
def test_anchor_loader_rejects_metadata_tampering(
    tmp_path: Path,
    field: str,
    replacement: object,
    match: str,
) -> None:
    mapping = _mapping()
    mapping[field] = replacement
    path, digest = _write(tmp_path, mapping)

    with pytest.raises(StudyProtocolError, match=match):
        load_confirmatory_robustness_anchor(
            path,
            flagship_narrative_stability_protocol(),
            expected_sha256=digest,
        )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("outcomes_type", "outcomes must be a list"),
        ("outcome_member", "outcomes must contain objects"),
        ("outcome_identity", "outcome identity"),
        ("contrasts_type", "contrasts must be a list"),
        ("contrast_member", "contrasts must contain objects"),
        ("contrast_value", "contrast values are invalid"),
        ("contrast_nonfinite", "contrast values must be finite"),
        ("h_order", "primary H order"),
        ("zero_direction", "one non-zero direction"),
        ("outcome_order", "outcome order or role"),
    ],
)
def test_anchor_loader_rejects_outcome_tampering(
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    mapping = _mapping()

    if mutation == "outcomes_type":
        mapping["outcomes"] = {}
    elif mutation == "outcome_member":
        mapping["outcomes"] = ["bad"]
    else:
        outcomes = cast(list[dict[str, Any]], mapping["outcomes"])
        primary_index = next(
            index for index, outcome in enumerate(outcomes) if outcome["role"] == "primary"
        )
        primary = dict(outcomes[primary_index])

        if mutation == "outcome_identity":
            primary["metric_name"] = 123
        elif mutation == "contrasts_type":
            primary["contrasts"] = {}
        elif mutation == "outcome_order":
            mapping["outcomes"] = list(reversed(outcomes))
        else:
            contrasts = [
                dict(item)
                for item in cast(
                    list[dict[str, Any]],
                    primary["contrasts"],
                )
            ]
            if mutation == "contrast_member":
                primary["contrasts"] = ["bad"]
            elif mutation == "contrast_value":
                contrasts[0].pop("mean_difference")
                primary["contrasts"] = contrasts
            elif mutation == "contrast_nonfinite":
                contrasts[0]["mean_difference"] = "NaN"
                primary["contrasts"] = contrasts
            elif mutation == "h_order":
                primary["contrasts"] = list(reversed(contrasts))
            elif mutation == "zero_direction":
                contrasts[0]["mean_difference"] = "0"
                primary["contrasts"] = contrasts
            else:
                raise AssertionError(mutation)

        if mutation != "outcome_order":
            updated = list(outcomes)
            updated[primary_index] = primary
            mapping["outcomes"] = updated

    path, digest = _write(tmp_path, mapping)
    with pytest.raises(StudyProtocolError, match=match):
        load_confirmatory_robustness_anchor(
            path,
            flagship_narrative_stability_protocol(),
            expected_sha256=digest,
        )


def test_seed_overlap_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = _protocol()
    seeds = robustness_seed_tuple(protocol, 2)

    monkeypatch.setattr(
        robustness_module,
        "precision_pilot_seed_tuple",
        lambda _: seeds,
    )
    with pytest.raises(StudyProtocolError, match="precision-pilot"):
        robustness_seed_tuple(protocol, 2)

    monkeypatch.undo()
    monkeypatch.setattr(
        robustness_module,
        "confirmatory_seed_tuple",
        lambda _protocol, _count: seeds,
    )
    with pytest.raises(StudyProtocolError, match="confirmatory"):
        robustness_seed_tuple(protocol, 2)


def test_homogeneity_helper_validation_paths() -> None:
    missing_experiment = cast(
        CalibrationExperimentResult,
        SimpleNamespace(scenario=SimpleNamespace(parameters=(("other", "1"),))),
    )
    with pytest.raises(StudyProtocolError, match="expose homogeneity"):
        robustness_module._experiment_h(missing_experiment)

    nonfinite_experiment = cast(
        CalibrationExperimentResult,
        SimpleNamespace(scenario=SimpleNamespace(parameters=(("homogeneity", "NaN"),))),
    )
    with pytest.raises(StudyProtocolError, match="finite"):
        robustness_module._experiment_h(nonfinite_experiment)

    missing_contrast = cast(
        PairedTreatmentContrast,
        SimpleNamespace(treatment_scenario=SimpleNamespace(parameters=(("other", "1"),))),
    )
    with pytest.raises(StudyProtocolError, match="expose homogeneity"):
        robustness_module._contrast_h(missing_contrast)

    nonfinite_contrast = cast(
        PairedTreatmentContrast,
        SimpleNamespace(treatment_scenario=SimpleNamespace(parameters=(("homogeneity", "NaN"),))),
    )
    with pytest.raises(StudyProtocolError, match="finite"):
        robustness_module._contrast_h(nonfinite_contrast)


def test_experiment_verifier_rejects_fingerprint_grid_and_seed_errors() -> None:
    protocol = _protocol()
    anchor = _anchor(protocol)
    regimes = _regimes(protocol)

    with pytest.raises(StudyProtocolError, match="protocol fingerprint"):
        verify_robustness_experiments(
            protocol,
            replace(anchor, protocol_fingerprint="0" * 64),
            regimes,
        )

    first = regimes[0]
    with pytest.raises(StudyProtocolError, match="full H grid"):
        verify_robustness_experiments(
            protocol,
            anchor,
            (
                replace(first, experiments=first.experiments[:-1]),
                *regimes[1:],
            ),
        )

    with pytest.raises(StudyProtocolError, match="H order"):
        verify_robustness_experiments(
            protocol,
            anchor,
            (
                replace(
                    first,
                    experiments=tuple(reversed(first.experiments)),
                ),
                *regimes[1:],
            ),
        )

    first_experiment = first.experiments[0]
    first_run = first_experiment.runs[0]
    bad_seed_experiment = replace(
        first_experiment,
        runs=(
            replace(
                first_run,
                spec=replace(
                    first_run.spec,
                    seed=first_run.spec.seed + 1,
                ),
            ),
            *first_experiment.runs[1:],
        ),
    )
    with pytest.raises(StudyProtocolError, match="seed tuple"):
        verify_robustness_experiments(
            protocol,
            anchor,
            (
                replace(
                    first,
                    experiments=(
                        bad_seed_experiment,
                        *first.experiments[1:],
                    ),
                ),
                *regimes[1:],
            ),
        )


def test_primary_outcome_audit_requires_reference() -> None:
    protocol = _protocol()
    regimes = _regimes(protocol)
    inference = infer_narrative_stability_sweep(
        regimes[0].experiments,
        metric_names=(protocol.primary_metric_names[0],),
        control_homogeneity=protocol.control_homogeneity,
        confidence_level=0.95,
    )

    with pytest.raises(StudyProtocolError, match="lacks reference"):
        robustness_module._outcome_audit(
            OutcomeRole.PRIMARY,
            protocol.primary_metric_names[0],
            inference[0].contrasts,
            None,
        )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"artifact_schema_version": "wrong"}, "artifact schema"),
        ({"source_git_commit": "bad"}, "source Git commit"),
        ({"robustness_seed_namespace": "wrong"}, "seed namespace"),
        ({"pilot_seed_overlap_count": 1}, "pilot seed overlap"),
        (
            {"confirmatory_seed_overlap_count": 1},
            "confirmatory seed overlap",
        ),
        ({"interval_scope": "wrong"}, "interval scope"),
        ({"inference_scope": "wrong"}, "inference scope"),
    ],
)
def test_artifact_constructor_guards(
    changes: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(StudyProtocolError, match=match):
        replace(
            _minimal_artifact(),
            **changes,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "level",
    [0.0, 1.0, float("nan"), float("inf")],
)
def test_builder_rejects_invalid_confidence_level(
    level: float,
) -> None:
    protocol = _protocol()
    with pytest.raises(StudyProtocolError, match="confidence_level"):
        build_robustness_audit_artifact(
            protocol,
            _anchor(protocol),
            _regimes(protocol),
            source_git_commit="e" * 40,
            confidence_level=level,
        )


def test_writer_rejects_wrong_type_and_temp_collision(
    tmp_path: Path,
) -> None:
    artifact = _minimal_artifact()
    target = tmp_path / "robustness.json"

    with pytest.raises(TypeError, match="RobustnessAuditArtifact"):
        write_robustness_audit_artifact(
            object(),  # type: ignore[arg-type]
            target,
        )

    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text("occupied", encoding="utf-8")
    with pytest.raises(StudyProtocolError, match="temporary"):
        write_robustness_audit_artifact(artifact, target)
