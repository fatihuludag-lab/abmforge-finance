"""Auditable execution and canonical artifact for the flagship precision pilot."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    infer_narrative_stability_sweep,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.calibration.summary import summarize_calibration_runs
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study.protocol import (
    FlagshipStudyProtocol,
    bundled_flagship_protocol_mapping,
    evaluate_precision_pilot,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)

_ARTIFACT_SCHEMA_VERSION = "precision-pilot-artifact-v1"
_DECISION_BASIS = "ci-half-width-only"
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _float_text(value: float) -> str:
    if not math.isfinite(value) or value < 0.0:
        raise StudyProtocolError("precision half-width must be finite and non-negative")
    return format(value, ".17g")


def _seed_fingerprint(seeds: tuple[int, ...]) -> str:
    payload = json.dumps(list(seeds), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _scenario_homogeneity(experiment: CalibrationExperimentResult) -> Decimal:
    parameters = dict(experiment.scenario.parameters)
    try:
        value = Decimal(parameters["homogeneity"])
    except (KeyError, ArithmeticError) as exc:
        raise StudyProtocolError(
            "precision experiment must expose a valid homogeneity parameter"
        ) from exc
    if not value.is_finite():
        raise StudyProtocolError("precision experiment homogeneity must be finite")
    return value


def _prefix_experiment(
    experiment: CalibrationExperimentResult,
    seed_count: int,
) -> CalibrationExperimentResult:
    runs = experiment.runs[:seed_count]
    if len(runs) != seed_count:
        raise StudyProtocolError("precision experiment has fewer runs than a prespecified prefix")
    return CalibrationExperimentResult(
        scenario=experiment.scenario,
        runs=runs,
        summary=summarize_calibration_runs(runs),
    )


def verify_bundled_flagship_protocol(protocol: FlagshipStudyProtocol) -> None:
    """Verify runtime protocol identity against the distributed JSON snapshot."""

    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if protocol.to_mapping() != bundled_flagship_protocol_mapping():
        raise StudyProtocolError(
            "runtime flagship protocol does not match the bundled JSON snapshot"
        )


def verify_precision_pilot_experiments(
    protocol: FlagshipStudyProtocol,
    experiments: tuple[CalibrationExperimentResult, ...],
) -> None:
    """Verify exact treatment, scenario, horizon, and seed provenance."""

    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if not isinstance(experiments, tuple) or len(experiments) != len(protocol.homogeneities):
        raise StudyProtocolError("precision experiments must match the prespecified treatment grid")
    if not all(isinstance(experiment, CalibrationExperimentResult) for experiment in experiments):
        raise StudyProtocolError(
            "precision experiments must contain CalibrationExperimentResult values"
        )

    expected_seeds = precision_pilot_seed_tuple(protocol)
    observed_h = tuple(_scenario_homogeneity(item) for item in experiments)
    if observed_h != protocol.homogeneities:
        raise StudyProtocolError(
            "precision experiment homogeneities must match protocol order exactly"
        )

    for homogeneity, experiment in zip(
        protocol.homogeneities,
        experiments,
        strict=True,
    ):
        expected_scenario = protocol.benchmark_config.scenario(homogeneity)
        if experiment.scenario != expected_scenario:
            raise StudyProtocolError(
                "precision experiment scenario does not exactly match the "
                "prespecified benchmark configuration"
            )
        seeds = tuple(run.spec.seed for run in experiment.runs)
        if seeds != expected_seeds:
            raise StudyProtocolError(
                "precision experiments must use the full prespecified pilot seed tuple"
            )


@dataclass(frozen=True, slots=True)
class PrecisionContrastWidth:
    """One treatment-vs-control CI half-width without an effect estimate."""

    treatment_homogeneity: Decimal
    ci_half_width: float

    def to_mapping(self) -> dict[str, object]:
        return {
            "treatment_homogeneity": _decimal_text(self.treatment_homogeneity),
            "ci_half_width": _float_text(self.ci_half_width),
        }


@dataclass(frozen=True, slots=True)
class PrecisionMetricArtifact:
    """Precision-only information for one primary metric at one seed count."""

    metric_name: str
    target_half_width: Decimal
    maximum_half_width: float
    contrasts: tuple[PrecisionContrastWidth, ...]
    criterion_met: bool

    def to_mapping(self) -> dict[str, object]:
        return {
            "metric_name": self.metric_name,
            "target_half_width": _decimal_text(self.target_half_width),
            "maximum_half_width": _float_text(self.maximum_half_width),
            "contrasts": [item.to_mapping() for item in self.contrasts],
            "criterion_met": self.criterion_met,
        }


@dataclass(frozen=True, slots=True)
class PrecisionCheckpointArtifact:
    """Precision-only decision data for one nested pilot prefix."""

    seed_count: int
    metrics: tuple[PrecisionMetricArtifact, ...]
    all_targets_met: bool

    def to_mapping(self) -> dict[str, object]:
        return {
            "seed_count": self.seed_count,
            "metrics": [item.to_mapping() for item in self.metrics],
            "all_targets_met": self.all_targets_met,
        }


@dataclass(frozen=True, slots=True)
class PrecisionPilotArtifact:
    """Canonical pilot decision artifact deliberately excluding effect estimates."""

    artifact_schema_version: str
    protocol_id: str
    protocol_version: str
    protocol_fingerprint: str
    source_git_commit: str
    pilot_seed_namespace: str
    pilot_seed_count: int
    pilot_seed_fingerprint: str
    candidate_seed_counts: tuple[int, ...]
    checkpoints: tuple[PrecisionCheckpointArtifact, ...]
    selected_seed_count: int | None
    confirmatory_eligible: bool
    decision_basis: str = _DECISION_BASIS
    effect_estimates_included: bool = False

    def __post_init__(self) -> None:
        if self.artifact_schema_version != _ARTIFACT_SCHEMA_VERSION:
            raise StudyProtocolError("unsupported precision artifact schema version")
        if not _GIT_SHA_PATTERN.fullmatch(self.source_git_commit):
            raise StudyProtocolError("source_git_commit must be a lowercase 40-character Git SHA")
        if self.decision_basis != _DECISION_BASIS:
            raise StudyProtocolError("precision artifact has an invalid decision basis")
        if self.effect_estimates_included:
            raise StudyProtocolError(
                "precision artifact must not include confirmatory effect estimates"
            )
        if self.confirmatory_eligible != (self.selected_seed_count is not None):
            raise StudyProtocolError("confirmatory eligibility must agree with selected_seed_count")

    def to_mapping(self) -> dict[str, object]:
        return {
            "artifact_schema_version": self.artifact_schema_version,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_fingerprint": self.protocol_fingerprint,
            "source_git_commit": self.source_git_commit,
            "pilot_seed_namespace": self.pilot_seed_namespace,
            "pilot_seed_count": self.pilot_seed_count,
            "pilot_seed_fingerprint": self.pilot_seed_fingerprint,
            "candidate_seed_counts": list(self.candidate_seed_counts),
            "checkpoints": [item.to_mapping() for item in self.checkpoints],
            "selected_seed_count": self.selected_seed_count,
            "confirmatory_eligible": self.confirmatory_eligible,
            "decision_basis": self.decision_basis,
            "effect_estimates_included": self.effect_estimates_included,
        }

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def canonical_bytes(self) -> bytes:
        return (self.canonical_json + "\n").encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def _contrast_homogeneity(contrast: object) -> Decimal:
    scenario = getattr(contrast, "treatment_scenario", None)
    if scenario is None:
        raise StudyProtocolError("paired contrast does not expose a treatment scenario")
    parameters = dict(scenario.parameters)
    try:
        value = Decimal(parameters["homogeneity"])
    except (KeyError, ArithmeticError) as exc:
        raise StudyProtocolError("paired contrast treatment must expose homogeneity") from exc
    if not value.is_finite():
        raise StudyProtocolError("paired contrast homogeneity must be finite")
    return value


def build_precision_pilot_artifact(
    protocol: FlagshipStudyProtocol,
    experiments: tuple[CalibrationExperimentResult, ...],
    *,
    source_git_commit: str,
) -> PrecisionPilotArtifact:
    """Build a precision-only artifact from fully verified pilot experiments."""

    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    verify_precision_pilot_experiments(protocol, experiments)

    report = evaluate_precision_pilot(protocol, experiments)
    target_by_name = {target.metric_name: target for target in protocol.precision_plan.targets}

    checkpoints: list[PrecisionCheckpointArtifact] = []
    for seed_count in protocol.precision_plan.candidate_seed_counts:
        prefix = tuple(_prefix_experiment(experiment, seed_count) for experiment in experiments)
        inference = infer_narrative_stability_sweep(
            prefix,
            metric_names=protocol.primary_metric_names,
            control_homogeneity=protocol.control_homogeneity,
            confidence_level=float(protocol.precision_plan.confidence_level),
        )

        metric_rows: list[PrecisionMetricArtifact] = []
        for metric in inference:
            contrast_rows: list[PrecisionContrastWidth] = []
            for contrast in metric.contrasts:
                half_width = (
                    contrast.confidence_interval_upper - contrast.confidence_interval_lower
                ) / 2.0
                contrast_rows.append(
                    PrecisionContrastWidth(
                        treatment_homogeneity=_contrast_homogeneity(contrast),
                        ci_half_width=half_width,
                    )
                )

            maximum = max(item.ci_half_width for item in contrast_rows)
            target = target_by_name[metric.metric_name]
            metric_rows.append(
                PrecisionMetricArtifact(
                    metric_name=metric.metric_name,
                    target_half_width=target.max_ci_half_width,
                    maximum_half_width=maximum,
                    contrasts=tuple(contrast_rows),
                    criterion_met=maximum <= float(target.max_ci_half_width),
                )
            )

        all_met = all(item.criterion_met for item in metric_rows)
        checkpoints.append(
            PrecisionCheckpointArtifact(
                seed_count=seed_count,
                metrics=tuple(metric_rows),
                all_targets_met=all_met,
            )
        )

    artifact = PrecisionPilotArtifact(
        artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_fingerprint=protocol.fingerprint,
        source_git_commit=source_git_commit,
        pilot_seed_namespace=protocol.pilot_seed_namespace,
        pilot_seed_count=len(precision_pilot_seed_tuple(protocol)),
        pilot_seed_fingerprint=_seed_fingerprint(precision_pilot_seed_tuple(protocol)),
        candidate_seed_counts=protocol.precision_plan.candidate_seed_counts,
        checkpoints=tuple(checkpoints),
        selected_seed_count=report.selected_seed_count,
        confirmatory_eligible=report.ready_for_confirmatory_run,
    )
    verify_precision_pilot_artifact(artifact, protocol)
    return artifact


def verify_precision_pilot_artifact(
    artifact: PrecisionPilotArtifact,
    protocol: FlagshipStudyProtocol,
) -> None:
    """Verify provenance and the prespecified width-only selection rule."""

    if not isinstance(artifact, PrecisionPilotArtifact):
        raise TypeError("artifact must be a PrecisionPilotArtifact")
    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")

    if artifact.protocol_id != protocol.protocol_id:
        raise StudyProtocolError("artifact protocol_id does not match protocol")
    if artifact.protocol_version != protocol.protocol_version:
        raise StudyProtocolError("artifact protocol_version does not match protocol")
    if artifact.protocol_fingerprint != protocol.fingerprint:
        raise StudyProtocolError("artifact protocol fingerprint does not match protocol")
    if artifact.pilot_seed_namespace != protocol.pilot_seed_namespace:
        raise StudyProtocolError("artifact pilot seed namespace does not match protocol")

    expected_seeds = precision_pilot_seed_tuple(protocol)
    if artifact.pilot_seed_count != len(expected_seeds):
        raise StudyProtocolError("artifact pilot seed count does not match protocol")
    if artifact.pilot_seed_fingerprint != _seed_fingerprint(expected_seeds):
        raise StudyProtocolError("artifact pilot seed fingerprint does not match protocol")
    if artifact.candidate_seed_counts != protocol.precision_plan.candidate_seed_counts:
        raise StudyProtocolError("artifact candidate seed counts do not match protocol")
    if tuple(item.seed_count for item in artifact.checkpoints) != (
        protocol.precision_plan.candidate_seed_counts
    ):
        raise StudyProtocolError("artifact checkpoints do not match candidate seed counts")

    target_by_name = {
        target.metric_name: target.max_ci_half_width for target in protocol.precision_plan.targets
    }
    expected_treatments = tuple(
        value for value in protocol.homogeneities if value != protocol.control_homogeneity
    )

    for checkpoint in artifact.checkpoints:
        if tuple(item.metric_name for item in checkpoint.metrics) != (
            protocol.primary_metric_names
        ):
            raise StudyProtocolError(
                "artifact checkpoint metric order does not match primary outcomes"
            )
        for metric in checkpoint.metrics:
            if metric.target_half_width != target_by_name[metric.metric_name]:
                raise StudyProtocolError("artifact precision target does not match protocol")
            if (
                tuple(item.treatment_homogeneity for item in metric.contrasts)
                != expected_treatments
            ):
                raise StudyProtocolError("artifact contrast order does not match treatment grid")
            observed_maximum = max(item.ci_half_width for item in metric.contrasts)
            if observed_maximum != metric.maximum_half_width:
                raise StudyProtocolError(
                    "artifact maximum half-width does not match contrast values"
                )
            if metric.criterion_met != (
                metric.maximum_half_width <= float(metric.target_half_width)
            ):
                raise StudyProtocolError("artifact metric precision decision is inconsistent")
        if checkpoint.all_targets_met != all(item.criterion_met for item in checkpoint.metrics):
            raise StudyProtocolError("artifact checkpoint precision decision is inconsistent")

    expected_selected = next(
        (item.seed_count for item in artifact.checkpoints if item.all_targets_met),
        None,
    )
    if artifact.selected_seed_count != expected_selected:
        raise StudyProtocolError(
            "artifact selected seed count violates the prespecified smallest-n rule"
        )


def write_precision_pilot_artifact(
    artifact: PrecisionPilotArtifact,
    path: str | os.PathLike[str],
) -> str:
    """Write canonical JSON exactly once and return its SHA-256 digest."""

    if not isinstance(artifact, PrecisionPilotArtifact):
        raise TypeError("artifact must be a PrecisionPilotArtifact")
    target = Path(path)
    if target.exists():
        raise StudyProtocolError(f"precision pilot artifact already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        raise StudyProtocolError(f"precision pilot temporary artifact already exists: {temporary}")
    temporary.write_bytes(artifact.canonical_bytes)
    os.replace(temporary, target)
    return artifact.sha256


def run_flagship_precision_pilot(
    *,
    source_git_commit: str,
) -> PrecisionPilotArtifact:
    """Run the frozen independent pilot and return only the precision artifact."""

    protocol = flagship_narrative_stability_protocol()
    verify_bundled_flagship_protocol(protocol)
    experiments = run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=precision_pilot_seed_tuple(protocol),
    )
    return build_precision_pilot_artifact(
        protocol,
        experiments,
        source_git_commit=source_git_commit,
    )
