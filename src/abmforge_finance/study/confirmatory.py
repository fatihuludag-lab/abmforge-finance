"""Prespecified confirmatory inference and Holm-family reporting."""

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
    PairedTreatmentContrast,
    infer_narrative_stability_sweep,
    paired_treatment_two_sided_p_value,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study.precision import verify_bundled_flagship_protocol
from abmforge_finance.study.protocol import (
    FlagshipStudyProtocol,
    MultiplicityMethod,
    OutcomeRole,
    confirmatory_seed_tuple,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)

OFFICIAL_FLAGSHIP_PRECISION_ARTIFACT_SHA256 = (
    "b43e9a1bfc6a40eadd0c38958068212a12d6feabfc8303c40917284a38d0be84"
)

_ARTIFACT_SCHEMA_VERSION = "confirmatory-artifact-v1"
_PRECISION_ARTIFACT_SCHEMA_VERSION = "precision-pilot-artifact-v1"
_INTERVAL_SCOPE = "nominal-per-contrast-not-familywise"
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        raise StudyProtocolError("confirmatory numeric values must be finite")
    return format(value, ".17g")


def _probability_text(value: float) -> str:
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise StudyProtocolError("confirmatory probabilities must be finite and in [0, 1]")
    return format(value, ".17g")


def _seed_fingerprint(seeds: tuple[int, ...]) -> str:
    payload = json.dumps(list(seeds), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _scenario_homogeneity_from_contrast(
    contrast: PairedTreatmentContrast,
) -> Decimal:
    parameters = dict(contrast.treatment_scenario.parameters)
    try:
        value = Decimal(parameters["homogeneity"])
    except (KeyError, ArithmeticError) as exc:
        raise StudyProtocolError("confirmatory contrast treatment must expose homogeneity") from exc
    if not value.is_finite():
        raise StudyProtocolError("confirmatory contrast homogeneity must be finite")
    return value


def _experiment_homogeneity(
    experiment: CalibrationExperimentResult,
) -> Decimal:
    parameters = dict(experiment.scenario.parameters)
    try:
        value = Decimal(parameters["homogeneity"])
    except (KeyError, ArithmeticError) as exc:
        raise StudyProtocolError("confirmatory experiment must expose homogeneity") from exc
    if not value.is_finite():
        raise StudyProtocolError("confirmatory experiment homogeneity must be finite")
    return value


@dataclass(frozen=True, slots=True)
class PrecisionPilotDecision:
    """Verified bridge from immutable pilot output to confirmatory execution."""

    artifact_sha256: str
    protocol_id: str
    protocol_version: str
    protocol_fingerprint: str
    precision_source_git_commit: str
    pilot_seed_namespace: str
    pilot_seed_count: int
    pilot_seed_fingerprint: str
    selected_seed_count: int

    def __post_init__(self) -> None:
        if not _SHA256_PATTERN.fullmatch(self.artifact_sha256):
            raise StudyProtocolError("precision artifact SHA-256 is invalid")
        if not _GIT_SHA_PATTERN.fullmatch(self.precision_source_git_commit):
            raise StudyProtocolError("precision source Git commit is invalid")
        if (
            isinstance(self.selected_seed_count, bool)
            or not isinstance(self.selected_seed_count, int)
            or self.selected_seed_count < 2
        ):
            raise StudyProtocolError("selected_seed_count must be an integer >= 2")


@dataclass(frozen=True, slots=True)
class HolmHypothesisResult:
    """One deterministic Holm step-down result."""

    hypothesis_id: str
    raw_p_value: float
    adjusted_p_value: float
    reject: bool


def holm_adjust(
    hypotheses: tuple[tuple[str, float], ...],
    *,
    familywise_alpha: float,
) -> tuple[HolmHypothesisResult, ...]:
    """Return Holm-adjusted p-values while preserving protocol input order."""

    if not isinstance(hypotheses, tuple) or not hypotheses:
        raise StudyProtocolError("Holm hypotheses must be a non-empty tuple")
    if isinstance(familywise_alpha, bool) or not isinstance(familywise_alpha, (int, float)):
        raise StudyProtocolError("familywise_alpha must be a real number")
    alpha = float(familywise_alpha)
    if not math.isfinite(alpha) or alpha <= 0.0 or alpha >= 1.0:
        raise StudyProtocolError("familywise_alpha must be strictly between 0 and 1")

    normalized: list[tuple[str, float]] = []
    for item in hypotheses:
        if not isinstance(item, tuple) or len(item) != 2:
            raise StudyProtocolError("each Holm hypothesis must be an (id, p-value) pair")
        hypothesis_id, raw = item
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
            raise StudyProtocolError("Holm hypothesis IDs must be non-empty strings")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise StudyProtocolError("Holm p-values must be real numbers")
        p_value = float(raw)
        if not math.isfinite(p_value) or p_value < 0.0 or p_value > 1.0:
            raise StudyProtocolError("Holm p-values must be finite and in [0, 1]")
        normalized.append((hypothesis_id.strip(), p_value))

    ids = tuple(item[0] for item in normalized)
    if len(set(ids)) != len(ids):
        raise StudyProtocolError("Holm hypothesis IDs must be unique")

    ordered = sorted(normalized, key=lambda item: (item[1], item[0]))
    count = len(ordered)
    adjusted_by_id: dict[str, float] = {}
    running = 0.0
    for rank, (hypothesis_id, raw_p_value) in enumerate(ordered, start=1):
        scaled = min(1.0, (count - rank + 1) * raw_p_value)
        running = max(running, scaled)
        adjusted_by_id[hypothesis_id] = running

    return tuple(
        HolmHypothesisResult(
            hypothesis_id=hypothesis_id,
            raw_p_value=p_value,
            adjusted_p_value=adjusted_by_id[hypothesis_id],
            reject=adjusted_by_id[hypothesis_id] <= alpha,
        )
        for hypothesis_id, p_value in normalized
    )


def load_precision_pilot_decision(
    path: str | os.PathLike[str],
    protocol: FlagshipStudyProtocol,
    *,
    expected_sha256: str = OFFICIAL_FLAGSHIP_PRECISION_ARTIFACT_SHA256,
) -> PrecisionPilotDecision:
    """Verify the immutable precision artifact and extract its locked decision."""

    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if not isinstance(expected_sha256, str) or not _SHA256_PATTERN.fullmatch(expected_sha256):
        raise StudyProtocolError("expected precision artifact SHA-256 is invalid")

    artifact_path = Path(path)
    try:
        payload = artifact_path.read_bytes()
    except OSError as exc:
        raise StudyProtocolError(f"unable to read precision artifact: {artifact_path}") from exc

    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise StudyProtocolError("precision artifact SHA-256 does not match expected value")

    try:
        mapping = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StudyProtocolError("precision artifact is not valid UTF-8 JSON") from exc
    if not isinstance(mapping, dict):
        raise StudyProtocolError("precision artifact JSON must be an object")

    expected_values: tuple[tuple[str, object], ...] = (
        ("artifact_schema_version", _PRECISION_ARTIFACT_SCHEMA_VERSION),
        ("protocol_id", protocol.protocol_id),
        ("protocol_version", protocol.protocol_version),
        ("protocol_fingerprint", protocol.fingerprint),
        ("pilot_seed_namespace", protocol.pilot_seed_namespace),
        ("decision_basis", "ci-half-width-only"),
        ("effect_estimates_included", False),
        ("confirmatory_eligible", True),
    )
    for field_name, expected in expected_values:
        if mapping.get(field_name) != expected:
            raise StudyProtocolError(
                f"precision artifact field {field_name!r} does not match the study contract"
            )

    if mapping.get("candidate_seed_counts") != list(protocol.precision_plan.candidate_seed_counts):
        raise StudyProtocolError("precision artifact candidate seed counts do not match protocol")

    expected_pilot_seeds = precision_pilot_seed_tuple(protocol)
    if mapping.get("pilot_seed_count") != len(expected_pilot_seeds):
        raise StudyProtocolError("precision artifact pilot seed count does not match protocol")
    if mapping.get("pilot_seed_fingerprint") != _seed_fingerprint(expected_pilot_seeds):
        raise StudyProtocolError(
            "precision artifact pilot seed fingerprint does not match protocol"
        )

    source_commit = mapping.get("source_git_commit")
    if not isinstance(source_commit, str) or not _GIT_SHA_PATTERN.fullmatch(source_commit):
        raise StudyProtocolError("precision artifact source_git_commit is invalid")

    selected = mapping.get("selected_seed_count")
    if (
        isinstance(selected, bool)
        or not isinstance(selected, int)
        or selected not in protocol.precision_plan.candidate_seed_counts
    ):
        raise StudyProtocolError(
            "precision artifact selected_seed_count is not a prespecified candidate"
        )

    checkpoints = mapping.get("checkpoints")
    if not isinstance(checkpoints, list):
        raise StudyProtocolError("precision artifact checkpoints must be a list")
    qualifying: list[int] = []
    observed_counts: list[int] = []
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            raise StudyProtocolError("precision artifact checkpoints must contain objects")
        seed_count = checkpoint.get("seed_count")
        all_targets_met = checkpoint.get("all_targets_met")
        if isinstance(seed_count, bool) or not isinstance(seed_count, int):
            raise StudyProtocolError("precision artifact checkpoint seed_count is invalid")
        if not isinstance(all_targets_met, bool):
            raise StudyProtocolError("precision artifact checkpoint all_targets_met is invalid")
        observed_counts.append(seed_count)
        if all_targets_met:
            qualifying.append(seed_count)

    if tuple(observed_counts) != protocol.precision_plan.candidate_seed_counts:
        raise StudyProtocolError("precision artifact checkpoint order does not match protocol")
    expected_selected = qualifying[0] if qualifying else None
    if selected != expected_selected:
        raise StudyProtocolError(
            "precision artifact selected_seed_count violates the smallest-n rule"
        )

    return PrecisionPilotDecision(
        artifact_sha256=actual_sha256,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_fingerprint=protocol.fingerprint,
        precision_source_git_commit=source_commit,
        pilot_seed_namespace=protocol.pilot_seed_namespace,
        pilot_seed_count=len(expected_pilot_seeds),
        pilot_seed_fingerprint=_seed_fingerprint(expected_pilot_seeds),
        selected_seed_count=selected,
    )


def verify_confirmatory_experiments(
    protocol: FlagshipStudyProtocol,
    decision: PrecisionPilotDecision,
    experiments: tuple[CalibrationExperimentResult, ...],
) -> None:
    """Verify treatment, scenario, and fresh-seed provenance exactly."""

    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if not isinstance(decision, PrecisionPilotDecision):
        raise TypeError("decision must be a PrecisionPilotDecision")
    if decision.protocol_fingerprint != protocol.fingerprint:
        raise StudyProtocolError(
            "precision decision protocol fingerprint does not match runtime protocol"
        )
    if not isinstance(experiments, tuple) or len(experiments) != len(protocol.homogeneities):
        raise StudyProtocolError(
            "confirmatory experiments must match the prespecified treatment grid"
        )
    if not all(isinstance(experiment, CalibrationExperimentResult) for experiment in experiments):
        raise StudyProtocolError(
            "confirmatory experiments must contain CalibrationExperimentResult values"
        )

    expected_seeds = confirmatory_seed_tuple(protocol, decision.selected_seed_count)
    pilot_seeds = precision_pilot_seed_tuple(protocol)
    if set(expected_seeds).intersection(pilot_seeds):
        raise StudyProtocolError("confirmatory seeds overlap precision-pilot seeds")

    observed_homogeneities = tuple(
        _experiment_homogeneity(experiment) for experiment in experiments
    )
    if observed_homogeneities != protocol.homogeneities:
        raise StudyProtocolError(
            "confirmatory experiment homogeneities must match protocol order exactly"
        )

    for homogeneity, experiment in zip(protocol.homogeneities, experiments, strict=True):
        if experiment.scenario != protocol.benchmark_config.scenario(homogeneity):
            raise StudyProtocolError(
                "confirmatory experiment scenario does not exactly match protocol"
            )
        observed_seeds = tuple(run.spec.seed for run in experiment.runs)
        if observed_seeds != expected_seeds:
            raise StudyProtocolError(
                "confirmatory experiments must use the exact confirmatory seed tuple"
            )


@dataclass(frozen=True, slots=True)
class ConfirmatoryContrastResult:
    """One treatment-vs-control paired estimate."""

    treatment_homogeneity: Decimal
    pair_count: int
    mean_difference: float
    sample_std_difference: float
    standard_error: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    hypothesis_id: str | None
    raw_p_value: float | None
    holm_adjusted_p_value: float | None
    holm_reject: bool | None

    def to_mapping(self) -> dict[str, object]:
        return {
            "treatment_homogeneity": _decimal_text(self.treatment_homogeneity),
            "pair_count": self.pair_count,
            "mean_difference": _float_text(self.mean_difference),
            "sample_std_difference": _float_text(self.sample_std_difference),
            "standard_error": _float_text(self.standard_error),
            "confidence_interval_lower": _float_text(self.confidence_interval_lower),
            "confidence_interval_upper": _float_text(self.confidence_interval_upper),
            "hypothesis_id": self.hypothesis_id,
            "raw_p_value": (
                None if self.raw_p_value is None else _probability_text(self.raw_p_value)
            ),
            "holm_adjusted_p_value": (
                None
                if self.holm_adjusted_p_value is None
                else _probability_text(self.holm_adjusted_p_value)
            ),
            "holm_reject": self.holm_reject,
        }


@dataclass(frozen=True, slots=True)
class ConfirmatoryOutcomeResult:
    """Prespecified outcome with role-aware paired contrasts."""

    metric_name: str
    role: OutcomeRole
    contrasts: tuple[ConfirmatoryContrastResult, ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "metric_name": self.metric_name,
            "role": self.role.value,
            "contrasts": [item.to_mapping() for item in self.contrasts],
        }


@dataclass(frozen=True, slots=True)
class ConfirmatoryArtifact:
    """Canonical confirmatory artifact with primary Holm inference."""

    artifact_schema_version: str
    protocol_id: str
    protocol_version: str
    protocol_fingerprint: str
    source_git_commit: str
    precision_artifact_sha256: str
    precision_source_git_commit: str
    selected_seed_count: int
    confirmatory_seed_namespace: str
    confirmatory_seed_count: int
    confirmatory_seed_fingerprint: str
    pilot_seed_overlap_count: int
    nominal_confidence_level: float
    interval_scope: str
    multiplicity_method: str
    familywise_alpha: float
    multiplicity_scope: str
    primary_hypothesis_count: int
    outcomes: tuple[ConfirmatoryOutcomeResult, ...]

    def __post_init__(self) -> None:
        if self.artifact_schema_version != _ARTIFACT_SCHEMA_VERSION:
            raise StudyProtocolError("unsupported confirmatory artifact schema version")
        if not _GIT_SHA_PATTERN.fullmatch(self.source_git_commit):
            raise StudyProtocolError("source_git_commit must be a lowercase 40-character Git SHA")
        if not _SHA256_PATTERN.fullmatch(self.precision_artifact_sha256):
            raise StudyProtocolError("precision_artifact_sha256 is invalid")
        if not _GIT_SHA_PATTERN.fullmatch(self.precision_source_git_commit):
            raise StudyProtocolError("precision_source_git_commit is invalid")
        if self.interval_scope != _INTERVAL_SCOPE:
            raise StudyProtocolError("confirmatory artifact interval scope is invalid")
        if self.pilot_seed_overlap_count != 0:
            raise StudyProtocolError("confirmatory artifact cannot contain pilot seed overlap")

    def to_mapping(self) -> dict[str, object]:
        return {
            "artifact_schema_version": self.artifact_schema_version,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_fingerprint": self.protocol_fingerprint,
            "source_git_commit": self.source_git_commit,
            "precision_artifact_sha256": self.precision_artifact_sha256,
            "precision_source_git_commit": (self.precision_source_git_commit),
            "selected_seed_count": self.selected_seed_count,
            "confirmatory_seed_namespace": self.confirmatory_seed_namespace,
            "confirmatory_seed_count": self.confirmatory_seed_count,
            "confirmatory_seed_fingerprint": (self.confirmatory_seed_fingerprint),
            "pilot_seed_overlap_count": self.pilot_seed_overlap_count,
            "nominal_confidence_level": _probability_text(self.nominal_confidence_level),
            "interval_scope": self.interval_scope,
            "multiplicity": {
                "method": self.multiplicity_method,
                "familywise_alpha": _probability_text(self.familywise_alpha),
                "scope": self.multiplicity_scope,
                "primary_hypothesis_count": (self.primary_hypothesis_count),
            },
            "outcomes": [item.to_mapping() for item in self.outcomes],
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


def _hypothesis_id(
    metric_name: str,
    treatment_homogeneity: Decimal,
    control_homogeneity: Decimal,
) -> str:
    return (
        f"{metric_name}|H={_decimal_text(treatment_homogeneity)}"
        f"-vs-{_decimal_text(control_homogeneity)}"
    )


def build_confirmatory_artifact(
    protocol: FlagshipStudyProtocol,
    decision: PrecisionPilotDecision,
    experiments: tuple[CalibrationExperimentResult, ...],
    *,
    source_git_commit: str,
) -> ConfirmatoryArtifact:
    """Build the prespecified role-aware confirmatory result artifact."""

    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if not isinstance(decision, PrecisionPilotDecision):
        raise TypeError("decision must be a PrecisionPilotDecision")
    if protocol.multiplicity_method is not MultiplicityMethod.HOLM:
        raise StudyProtocolError("flagship confirmatory inference requires Holm multiplicity")

    verify_confirmatory_experiments(protocol, decision, experiments)

    nominal_confidence_level = 1.0 - float(protocol.familywise_alpha)
    outcome_names = tuple(outcome.metric_name for outcome in protocol.outcomes)
    inference = infer_narrative_stability_sweep(
        experiments,
        metric_names=outcome_names,
        control_homogeneity=protocol.control_homogeneity,
        confidence_level=nominal_confidence_level,
    )
    inference_by_metric = {item.metric_name: item for item in inference}

    raw_primary: list[tuple[str, float]] = []
    for outcome in protocol.outcomes:
        if outcome.role is not OutcomeRole.PRIMARY:
            continue
        metric_inference = inference_by_metric[outcome.metric_name]
        for contrast in metric_inference.contrasts:
            treatment_h = _scenario_homogeneity_from_contrast(contrast)
            hypothesis_id = _hypothesis_id(
                outcome.metric_name,
                treatment_h,
                protocol.control_homogeneity,
            )
            raw_primary.append(
                (
                    hypothesis_id,
                    paired_treatment_two_sided_p_value(contrast),
                )
            )

    if len(raw_primary) != protocol.primary_hypothesis_count:
        raise StudyProtocolError("confirmatory primary hypothesis count does not match protocol")

    holm_results = {
        item.hypothesis_id: item
        for item in holm_adjust(
            tuple(raw_primary),
            familywise_alpha=float(protocol.familywise_alpha),
        )
    }

    outcome_rows: list[ConfirmatoryOutcomeResult] = []
    for outcome in protocol.outcomes:
        metric_inference = inference_by_metric[outcome.metric_name]
        contrast_rows: list[ConfirmatoryContrastResult] = []
        for contrast in metric_inference.contrasts:
            treatment_h = _scenario_homogeneity_from_contrast(contrast)
            contrast_hypothesis_id: str | None = None
            raw_p_value: float | None = None
            adjusted_p_value: float | None = None
            holm_reject: bool | None = None

            if outcome.role is OutcomeRole.PRIMARY:
                contrast_hypothesis_id = _hypothesis_id(
                    outcome.metric_name,
                    treatment_h,
                    protocol.control_homogeneity,
                )
                holm_result = holm_results[contrast_hypothesis_id]
                raw_p_value = holm_result.raw_p_value
                adjusted_p_value = holm_result.adjusted_p_value
                holm_reject = holm_result.reject

            contrast_rows.append(
                ConfirmatoryContrastResult(
                    treatment_homogeneity=treatment_h,
                    pair_count=contrast.pair_count,
                    mean_difference=contrast.mean_difference,
                    sample_std_difference=(contrast.sample_std_difference),
                    standard_error=contrast.standard_error,
                    confidence_interval_lower=(contrast.confidence_interval_lower),
                    confidence_interval_upper=(contrast.confidence_interval_upper),
                    hypothesis_id=contrast_hypothesis_id,
                    raw_p_value=raw_p_value,
                    holm_adjusted_p_value=adjusted_p_value,
                    holm_reject=holm_reject,
                )
            )
        outcome_rows.append(
            ConfirmatoryOutcomeResult(
                metric_name=outcome.metric_name,
                role=outcome.role,
                contrasts=tuple(contrast_rows),
            )
        )

    confirmatory_seeds = confirmatory_seed_tuple(protocol, decision.selected_seed_count)
    artifact = ConfirmatoryArtifact(
        artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_fingerprint=protocol.fingerprint,
        source_git_commit=source_git_commit,
        precision_artifact_sha256=decision.artifact_sha256,
        precision_source_git_commit=(decision.precision_source_git_commit),
        selected_seed_count=decision.selected_seed_count,
        confirmatory_seed_namespace=(protocol.confirmatory_seed_namespace),
        confirmatory_seed_count=len(confirmatory_seeds),
        confirmatory_seed_fingerprint=_seed_fingerprint(confirmatory_seeds),
        pilot_seed_overlap_count=len(
            set(confirmatory_seeds).intersection(precision_pilot_seed_tuple(protocol))
        ),
        nominal_confidence_level=nominal_confidence_level,
        interval_scope=_INTERVAL_SCOPE,
        multiplicity_method=protocol.multiplicity_method.value,
        familywise_alpha=float(protocol.familywise_alpha),
        multiplicity_scope=protocol.multiplicity_scope,
        primary_hypothesis_count=protocol.primary_hypothesis_count,
        outcomes=tuple(outcome_rows),
    )
    verify_confirmatory_artifact(artifact, protocol, decision)
    return artifact


def verify_confirmatory_artifact(
    artifact: ConfirmatoryArtifact,
    protocol: FlagshipStudyProtocol,
    decision: PrecisionPilotDecision,
) -> None:
    """Verify provenance, role separation, and exact Holm decisions."""

    if not isinstance(artifact, ConfirmatoryArtifact):
        raise TypeError("artifact must be a ConfirmatoryArtifact")
    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if not isinstance(decision, PrecisionPilotDecision):
        raise TypeError("decision must be a PrecisionPilotDecision")

    if artifact.protocol_id != protocol.protocol_id:
        raise StudyProtocolError("confirmatory artifact protocol_id mismatch")
    if artifact.protocol_version != protocol.protocol_version:
        raise StudyProtocolError("confirmatory artifact protocol_version mismatch")
    if artifact.protocol_fingerprint != protocol.fingerprint:
        raise StudyProtocolError("confirmatory artifact protocol fingerprint mismatch")
    if artifact.precision_artifact_sha256 != decision.artifact_sha256:
        raise StudyProtocolError("confirmatory precision artifact SHA mismatch")
    if artifact.precision_source_git_commit != decision.precision_source_git_commit:
        raise StudyProtocolError("confirmatory precision source commit mismatch")
    if artifact.selected_seed_count != decision.selected_seed_count:
        raise StudyProtocolError("confirmatory selected seed count mismatch")
    if artifact.confirmatory_seed_namespace != protocol.confirmatory_seed_namespace:
        raise StudyProtocolError("confirmatory seed namespace mismatch")

    expected_seeds = confirmatory_seed_tuple(protocol, decision.selected_seed_count)
    if artifact.confirmatory_seed_count != len(expected_seeds):
        raise StudyProtocolError("confirmatory seed count mismatch")
    if artifact.confirmatory_seed_fingerprint != _seed_fingerprint(expected_seeds):
        raise StudyProtocolError("confirmatory seed fingerprint mismatch")
    if artifact.pilot_seed_overlap_count != 0:
        raise StudyProtocolError("confirmatory pilot seed overlap must be zero")

    expected_level = 1.0 - float(protocol.familywise_alpha)
    if artifact.nominal_confidence_level != expected_level:
        raise StudyProtocolError("confirmatory nominal confidence level mismatch")
    if artifact.multiplicity_method != protocol.multiplicity_method.value:
        raise StudyProtocolError("confirmatory multiplicity method mismatch")
    if artifact.familywise_alpha != float(protocol.familywise_alpha):
        raise StudyProtocolError("confirmatory familywise alpha mismatch")
    if artifact.multiplicity_scope != protocol.multiplicity_scope:
        raise StudyProtocolError("confirmatory multiplicity scope mismatch")
    if artifact.primary_hypothesis_count != protocol.primary_hypothesis_count:
        raise StudyProtocolError("confirmatory primary hypothesis count mismatch")

    if tuple((item.metric_name, item.role) for item in artifact.outcomes) != tuple(
        (item.metric_name, item.role) for item in protocol.outcomes
    ):
        raise StudyProtocolError("confirmatory outcome order or role mismatch")

    expected_treatments = tuple(
        value for value in protocol.homogeneities if value != protocol.control_homogeneity
    )
    raw_primary: list[tuple[str, float]] = []
    for outcome in artifact.outcomes:
        if tuple(item.treatment_homogeneity for item in outcome.contrasts) != expected_treatments:
            raise StudyProtocolError("confirmatory treatment contrast order mismatch")
        if any(item.pair_count != decision.selected_seed_count for item in outcome.contrasts):
            raise StudyProtocolError("confirmatory pair count mismatch")

        for contrast in outcome.contrasts:
            if outcome.role is OutcomeRole.PRIMARY:
                expected_id = _hypothesis_id(
                    outcome.metric_name,
                    contrast.treatment_homogeneity,
                    protocol.control_homogeneity,
                )
                if contrast.hypothesis_id != expected_id:
                    raise StudyProtocolError("confirmatory primary hypothesis ID mismatch")
                if (
                    contrast.raw_p_value is None
                    or contrast.holm_adjusted_p_value is None
                    or contrast.holm_reject is None
                ):
                    raise StudyProtocolError(
                        "confirmatory primary contrasts require Holm inference fields"
                    )
                raw_primary.append((expected_id, contrast.raw_p_value))
            elif (
                contrast.hypothesis_id is not None
                or contrast.raw_p_value is not None
                or contrast.holm_adjusted_p_value is not None
                or contrast.holm_reject is not None
            ):
                raise StudyProtocolError("non-primary outcomes must not expose significance fields")

    if len(raw_primary) != protocol.primary_hypothesis_count:
        raise StudyProtocolError("confirmatory primary hypothesis family size mismatch")

    expected_holm = {
        item.hypothesis_id: item
        for item in holm_adjust(
            tuple(raw_primary),
            familywise_alpha=float(protocol.familywise_alpha),
        )
    }
    for outcome in artifact.outcomes:
        if outcome.role is not OutcomeRole.PRIMARY:
            continue
        for contrast in outcome.contrasts:
            assert contrast.hypothesis_id is not None
            expected = expected_holm[contrast.hypothesis_id]
            if contrast.holm_adjusted_p_value != expected.adjusted_p_value:
                raise StudyProtocolError("confirmatory Holm adjusted p-value mismatch")
            if contrast.holm_reject != expected.reject:
                raise StudyProtocolError("confirmatory Holm rejection decision mismatch")


def write_confirmatory_artifact(
    artifact: ConfirmatoryArtifact,
    path: str | os.PathLike[str],
) -> str:
    """Write canonical confirmatory JSON exactly once and return SHA-256."""

    if not isinstance(artifact, ConfirmatoryArtifact):
        raise TypeError("artifact must be a ConfirmatoryArtifact")
    target = Path(path)
    if target.exists():
        raise StudyProtocolError(f"confirmatory artifact already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        raise StudyProtocolError(f"confirmatory temporary artifact already exists: {temporary}")
    temporary.write_bytes(artifact.canonical_bytes)
    os.replace(temporary, target)
    return artifact.sha256


def run_flagship_confirmatory(
    *,
    precision_artifact_path: str | os.PathLike[str],
    source_git_commit: str,
    expected_precision_sha256: str = (OFFICIAL_FLAGSHIP_PRECISION_ARTIFACT_SHA256),
) -> ConfirmatoryArtifact:
    """Run the frozen confirmatory study after verifying precision output."""

    protocol = flagship_narrative_stability_protocol()
    verify_bundled_flagship_protocol(protocol)
    decision = load_precision_pilot_decision(
        precision_artifact_path,
        protocol,
        expected_sha256=expected_precision_sha256,
    )
    seeds = confirmatory_seed_tuple(protocol, decision.selected_seed_count)
    experiments = run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=seeds,
    )
    return build_confirmatory_artifact(
        protocol,
        decision,
        experiments,
        source_git_commit=source_git_commit,
    )
