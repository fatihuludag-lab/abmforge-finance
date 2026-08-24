"""Prespecified flagship robustness execution and estimation-only audit."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    PairedTreatmentContrast,
    infer_narrative_stability_sweep,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study.precision import verify_bundled_flagship_protocol
from abmforge_finance.study.protocol import (
    FlagshipStudyProtocol,
    OutcomeRole,
    apply_robustness_regime,
    confirmatory_seed_tuple,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
    study_seed_tuple,
)

OFFICIAL_FLAGSHIP_CONFIRMATORY_ARTIFACT_SHA256 = (
    "9e78c74483ca20c16fdf3dca8f518957959ec66e3d810518a78e1cb5402831ed"
)

_ROBUSTNESS_SEED_NAMESPACE = "robustness-v1"
_ARTIFACT_SCHEMA_VERSION = "robustness-audit-artifact-v1"
_INFERENCE_SCOPE = "estimation-only-no-additional-multiplicity-family"
_INTERVAL_SCOPE = "nominal-per-contrast-not-familywise"
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        raise StudyProtocolError("robustness numeric values must be finite")
    return format(value, ".17g")


def _seed_fingerprint(seeds: tuple[int, ...]) -> str:
    payload = json.dumps(list(seeds), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sign(value: float) -> int:
    if not math.isfinite(value):
        raise StudyProtocolError("robustness effects must be finite")
    return 1 if value > 0.0 else -1 if value < 0.0 else 0


def _experiment_h(experiment: CalibrationExperimentResult) -> Decimal:
    try:
        value = Decimal(dict(experiment.scenario.parameters)["homogeneity"])
    except (KeyError, ArithmeticError) as exc:
        raise StudyProtocolError("robustness experiment must expose homogeneity") from exc
    if not value.is_finite():
        raise StudyProtocolError("robustness homogeneity must be finite")
    return value


def _contrast_h(contrast: PairedTreatmentContrast) -> Decimal:
    try:
        value = Decimal(dict(contrast.treatment_scenario.parameters)["homogeneity"])
    except (KeyError, ArithmeticError) as exc:
        raise StudyProtocolError("robustness contrast must expose homogeneity") from exc
    if not value.is_finite():
        raise StudyProtocolError("robustness contrast homogeneity must be finite")
    return value


@dataclass(frozen=True, slots=True)
class ConfirmatoryRobustnessAnchor:
    artifact_sha256: str
    source_git_commit: str
    protocol_fingerprint: str
    precision_artifact_sha256: str
    selected_seed_count: int
    confirmatory_seed_fingerprint: str
    primary_effects: tuple[tuple[str, tuple[tuple[Decimal, float], ...]], ...]

    def primary_effect_map(self) -> dict[str, dict[Decimal, float]]:
        return {metric: dict(rows) for metric, rows in self.primary_effects}


def load_confirmatory_robustness_anchor(
    path: str | os.PathLike[str],
    protocol: FlagshipStudyProtocol,
    *,
    expected_sha256: str = OFFICIAL_FLAGSHIP_CONFIRMATORY_ARTIFACT_SHA256,
) -> ConfirmatoryRobustnessAnchor:
    """Verify the immutable confirmatory artifact and extract primary effects."""

    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise StudyProtocolError("expected confirmatory SHA-256 is invalid")

    artifact_path = Path(path)
    try:
        payload = artifact_path.read_bytes()
    except OSError as exc:
        raise StudyProtocolError(f"unable to read confirmatory artifact: {artifact_path}") from exc

    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != expected_sha256:
        raise StudyProtocolError("confirmatory artifact SHA-256 mismatch")

    try:
        mapping = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StudyProtocolError("confirmatory artifact is not valid UTF-8 JSON") from exc
    if not isinstance(mapping, dict):
        raise StudyProtocolError("confirmatory artifact JSON must be an object")

    required = {
        "artifact_schema_version": "confirmatory-artifact-v1",
        "protocol_id": protocol.protocol_id,
        "protocol_version": protocol.protocol_version,
        "protocol_fingerprint": protocol.fingerprint,
        "confirmatory_seed_namespace": protocol.confirmatory_seed_namespace,
        "pilot_seed_overlap_count": 0,
    }
    for field, expected in required.items():
        if mapping.get(field) != expected:
            raise StudyProtocolError(f"confirmatory field {field!r} does not match protocol")

    source_commit = mapping.get("source_git_commit")
    precision_hash = mapping.get("precision_artifact_sha256")
    selected = mapping.get("selected_seed_count")
    if not isinstance(source_commit, str) or not _GIT_SHA.fullmatch(source_commit):
        raise StudyProtocolError("confirmatory source_git_commit is invalid")
    if not isinstance(precision_hash, str) or not _SHA256.fullmatch(precision_hash):
        raise StudyProtocolError("confirmatory precision artifact SHA-256 is invalid")
    if (
        isinstance(selected, bool)
        or not isinstance(selected, int)
        or selected not in protocol.precision_plan.candidate_seed_counts
    ):
        raise StudyProtocolError("confirmatory selected_seed_count is not prespecified")

    seeds = confirmatory_seed_tuple(protocol, selected)
    seed_fingerprint = _seed_fingerprint(seeds)
    if mapping.get("confirmatory_seed_count") != len(seeds):
        raise StudyProtocolError("confirmatory seed count mismatch")
    if mapping.get("confirmatory_seed_fingerprint") != seed_fingerprint:
        raise StudyProtocolError("confirmatory seed fingerprint mismatch")

    outcomes = mapping.get("outcomes")
    if not isinstance(outcomes, list):
        raise StudyProtocolError("confirmatory outcomes must be a list")

    expected_outcomes = tuple((item.metric_name, item.role.value) for item in protocol.outcomes)
    observed_outcomes: list[tuple[str, str]] = []
    expected_h = tuple(
        value for value in protocol.homogeneities if value != protocol.control_homogeneity
    )
    primary_effects: list[tuple[str, tuple[tuple[Decimal, float], ...]]] = []

    for outcome in outcomes:
        if not isinstance(outcome, dict):
            raise StudyProtocolError("confirmatory outcomes must contain objects")
        metric = outcome.get("metric_name")
        role = outcome.get("role")
        if not isinstance(metric, str) or not isinstance(role, str):
            raise StudyProtocolError("confirmatory outcome identity is invalid")
        observed_outcomes.append((metric, role))
        if role != OutcomeRole.PRIMARY.value:
            continue

        contrasts = outcome.get("contrasts")
        if not isinstance(contrasts, list):
            raise StudyProtocolError("primary confirmatory contrasts must be a list")
        rows: list[tuple[Decimal, float]] = []
        for contrast in contrasts:
            if not isinstance(contrast, dict):
                raise StudyProtocolError("primary confirmatory contrasts must contain objects")
            try:
                h = Decimal(str(contrast["treatment_homogeneity"]))
                effect = float(contrast["mean_difference"])
            except (KeyError, ArithmeticError, TypeError, ValueError) as exc:
                raise StudyProtocolError(
                    "primary confirmatory contrast values are invalid"
                ) from exc
            if not h.is_finite() or not math.isfinite(effect):
                raise StudyProtocolError("primary confirmatory contrast values must be finite")
            rows.append((h, effect))
        if tuple(h for h, _ in rows) != expected_h:
            raise StudyProtocolError("confirmatory primary H order mismatch")
        directions = tuple(_sign(effect) for _, effect in rows)
        if 0 in directions or len(set(directions)) != 1:
            raise StudyProtocolError("confirmatory primary effects require one non-zero direction")
        primary_effects.append((metric, tuple(rows)))

    if tuple(observed_outcomes) != expected_outcomes:
        raise StudyProtocolError("confirmatory outcome order or role mismatch")
    if tuple(metric for metric, _ in primary_effects) != protocol.primary_metric_names:
        raise StudyProtocolError("confirmatory primary outcome set mismatch")

    return ConfirmatoryRobustnessAnchor(
        artifact_sha256=actual_hash,
        source_git_commit=source_commit,
        protocol_fingerprint=protocol.fingerprint,
        precision_artifact_sha256=precision_hash,
        selected_seed_count=selected,
        confirmatory_seed_fingerprint=seed_fingerprint,
        primary_effects=tuple(primary_effects),
    )


def robustness_seed_tuple(
    protocol: FlagshipStudyProtocol,
    selected_seed_count: int,
) -> tuple[int, ...]:
    """Fresh shared CRN tuple for every prespecified robustness regime."""

    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if selected_seed_count not in protocol.precision_plan.candidate_seed_counts:
        raise StudyProtocolError("robustness seed count must be a prespecified candidate")
    seeds = study_seed_tuple(
        protocol,
        namespace=_ROBUSTNESS_SEED_NAMESPACE,
        count=selected_seed_count,
    )
    if set(seeds).intersection(precision_pilot_seed_tuple(protocol)):
        raise StudyProtocolError("robustness seeds overlap precision-pilot seeds")
    if set(seeds).intersection(confirmatory_seed_tuple(protocol, selected_seed_count)):
        raise StudyProtocolError("robustness seeds overlap confirmatory seeds")
    return seeds


@dataclass(frozen=True, slots=True)
class RobustnessRegimeExperiments:
    regime_id: str
    experiments: tuple[CalibrationExperimentResult, ...]


def verify_robustness_experiments(
    protocol: FlagshipStudyProtocol,
    anchor: ConfirmatoryRobustnessAnchor,
    regimes: tuple[RobustnessRegimeExperiments, ...],
) -> None:
    """Verify exact regime order, H grid, scenarios, and common seeds."""

    if anchor.protocol_fingerprint != protocol.fingerprint:
        raise StudyProtocolError("robustness anchor protocol fingerprint mismatch")
    expected_ids = tuple(regime.regime_id for regime in protocol.robustness_regimes)
    if tuple(item.regime_id for item in regimes) != expected_ids:
        raise StudyProtocolError("robustness regime order mismatch")

    expected_seeds = robustness_seed_tuple(protocol, anchor.selected_seed_count)
    for item in regimes:
        if len(item.experiments) != len(protocol.homogeneities):
            raise StudyProtocolError("robustness regime must contain the full H grid")
        if tuple(_experiment_h(exp) for exp in item.experiments) != (protocol.homogeneities):
            raise StudyProtocolError("robustness H order mismatch")
        config = apply_robustness_regime(protocol, item.regime_id)
        for h, experiment in zip(protocol.homogeneities, item.experiments, strict=True):
            if experiment.scenario != config.scenario(h):
                raise StudyProtocolError("robustness scenario does not match protocol regime")
            if tuple(run.spec.seed for run in experiment.runs) != expected_seeds:
                raise StudyProtocolError("robustness seed tuple mismatch")


@dataclass(frozen=True, slots=True)
class RobustnessContrastResult:
    treatment_homogeneity: Decimal
    pair_count: int
    mean_difference: float
    standard_error: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    confirmatory_reference_effect: float | None
    effect_ratio_to_confirmatory: float | None
    confirmatory_direction_preserved: bool | None

    def to_mapping(self) -> dict[str, object]:
        return {
            "treatment_homogeneity": _decimal_text(self.treatment_homogeneity),
            "pair_count": self.pair_count,
            "mean_difference": _float_text(self.mean_difference),
            "standard_error": _float_text(self.standard_error),
            "confidence_interval_lower": _float_text(self.confidence_interval_lower),
            "confidence_interval_upper": _float_text(self.confidence_interval_upper),
            "confirmatory_reference_effect": (
                None
                if self.confirmatory_reference_effect is None
                else _float_text(self.confirmatory_reference_effect)
            ),
            "effect_ratio_to_confirmatory": (
                None
                if self.effect_ratio_to_confirmatory is None
                else _float_text(self.effect_ratio_to_confirmatory)
            ),
            "confirmatory_direction_preserved": (self.confirmatory_direction_preserved),
        }


@dataclass(frozen=True, slots=True)
class RobustnessOutcomeAudit:
    metric_name: str
    role: OutcomeRole
    contrasts: tuple[RobustnessContrastResult, ...]
    direction_preserved_all_contrasts: bool | None
    dose_response_non_decreasing: bool | None
    minimum_effect_ratio_to_confirmatory: float | None
    maximum_effect_ratio_to_confirmatory: float | None

    def to_mapping(self) -> dict[str, object]:
        return {
            "metric_name": self.metric_name,
            "role": self.role.value,
            "contrasts": [item.to_mapping() for item in self.contrasts],
            "direction_preserved_all_contrasts": (self.direction_preserved_all_contrasts),
            "dose_response_non_decreasing": self.dose_response_non_decreasing,
            "minimum_effect_ratio_to_confirmatory": (
                None
                if self.minimum_effect_ratio_to_confirmatory is None
                else _float_text(self.minimum_effect_ratio_to_confirmatory)
            ),
            "maximum_effect_ratio_to_confirmatory": (
                None
                if self.maximum_effect_ratio_to_confirmatory is None
                else _float_text(self.maximum_effect_ratio_to_confirmatory)
            ),
        }


@dataclass(frozen=True, slots=True)
class RobustnessRegimeAudit:
    regime_id: str
    parameter_name: str
    parameter_value: str
    outcomes: tuple[RobustnessOutcomeAudit, ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "regime_id": self.regime_id,
            "parameter_name": self.parameter_name,
            "parameter_value": self.parameter_value,
            "outcomes": [item.to_mapping() for item in self.outcomes],
        }


@dataclass(frozen=True, slots=True)
class RobustnessAuditArtifact:
    artifact_schema_version: str
    protocol_id: str
    protocol_version: str
    protocol_fingerprint: str
    source_git_commit: str
    confirmatory_artifact_sha256: str
    confirmatory_source_git_commit: str
    selected_seed_count: int
    robustness_seed_namespace: str
    robustness_seed_count: int
    robustness_seed_fingerprint: str
    pilot_seed_overlap_count: int
    confirmatory_seed_overlap_count: int
    confidence_level: float
    interval_scope: str
    inference_scope: str
    regimes: tuple[RobustnessRegimeAudit, ...]

    def __post_init__(self) -> None:
        if self.artifact_schema_version != _ARTIFACT_SCHEMA_VERSION:
            raise StudyProtocolError("invalid robustness artifact schema")
        if not _GIT_SHA.fullmatch(self.source_git_commit):
            raise StudyProtocolError("invalid robustness source Git commit")
        if self.robustness_seed_namespace != _ROBUSTNESS_SEED_NAMESPACE:
            raise StudyProtocolError("invalid robustness seed namespace")
        if self.pilot_seed_overlap_count != 0:
            raise StudyProtocolError("pilot seed overlap must be zero")
        if self.confirmatory_seed_overlap_count != 0:
            raise StudyProtocolError("confirmatory seed overlap must be zero")
        if self.interval_scope != _INTERVAL_SCOPE:
            raise StudyProtocolError("invalid robustness interval scope")
        if self.inference_scope != _INFERENCE_SCOPE:
            raise StudyProtocolError("invalid robustness inference scope")

    def to_mapping(self) -> dict[str, object]:
        return {
            "artifact_schema_version": self.artifact_schema_version,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_fingerprint": self.protocol_fingerprint,
            "source_git_commit": self.source_git_commit,
            "confirmatory_artifact_sha256": (self.confirmatory_artifact_sha256),
            "confirmatory_source_git_commit": (self.confirmatory_source_git_commit),
            "selected_seed_count": self.selected_seed_count,
            "robustness_seed_namespace": self.robustness_seed_namespace,
            "robustness_seed_count": self.robustness_seed_count,
            "robustness_seed_fingerprint": (self.robustness_seed_fingerprint),
            "pilot_seed_overlap_count": self.pilot_seed_overlap_count,
            "confirmatory_seed_overlap_count": (self.confirmatory_seed_overlap_count),
            "confidence_level": _float_text(self.confidence_level),
            "interval_scope": self.interval_scope,
            "inference_scope": self.inference_scope,
            "regimes": [item.to_mapping() for item in self.regimes],
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


def _outcome_audit(
    outcome_role: OutcomeRole,
    metric_name: str,
    contrasts: tuple[PairedTreatmentContrast, ...],
    reference: dict[Decimal, float] | None,
) -> RobustnessOutcomeAudit:
    if outcome_role is not OutcomeRole.PRIMARY:
        rows = tuple(
            RobustnessContrastResult(
                treatment_homogeneity=_contrast_h(item),
                pair_count=item.pair_count,
                mean_difference=item.mean_difference,
                standard_error=item.standard_error,
                confidence_interval_lower=item.confidence_interval_lower,
                confidence_interval_upper=item.confidence_interval_upper,
                confirmatory_reference_effect=None,
                effect_ratio_to_confirmatory=None,
                confirmatory_direction_preserved=None,
            )
            for item in contrasts
        )
        return RobustnessOutcomeAudit(
            metric_name=metric_name,
            role=outcome_role,
            contrasts=rows,
            direction_preserved_all_contrasts=None,
            dose_response_non_decreasing=None,
            minimum_effect_ratio_to_confirmatory=None,
            maximum_effect_ratio_to_confirmatory=None,
        )

    if reference is None:
        raise StudyProtocolError("primary robustness outcome lacks reference")
    direction = _sign(next(iter(reference.values())))
    rows_list: list[RobustnessContrastResult] = []
    ratios: list[float] = []
    oriented: list[float] = []
    flags: list[bool] = []
    for contrast in contrasts:
        h = _contrast_h(contrast)
        reference_effect = reference[h]
        ratio = contrast.mean_difference / reference_effect
        preserved = _sign(contrast.mean_difference) == direction
        rows_list.append(
            RobustnessContrastResult(
                treatment_homogeneity=h,
                pair_count=contrast.pair_count,
                mean_difference=contrast.mean_difference,
                standard_error=contrast.standard_error,
                confidence_interval_lower=contrast.confidence_interval_lower,
                confidence_interval_upper=contrast.confidence_interval_upper,
                confirmatory_reference_effect=reference_effect,
                effect_ratio_to_confirmatory=ratio,
                confirmatory_direction_preserved=preserved,
            )
        )
        ratios.append(ratio)
        oriented.append(contrast.mean_difference * direction)
        flags.append(preserved)

    dose_response = all(right >= left for left, right in pairwise(oriented))
    return RobustnessOutcomeAudit(
        metric_name=metric_name,
        role=outcome_role,
        contrasts=tuple(rows_list),
        direction_preserved_all_contrasts=all(flags),
        dose_response_non_decreasing=dose_response,
        minimum_effect_ratio_to_confirmatory=min(ratios),
        maximum_effect_ratio_to_confirmatory=max(ratios),
    )


def build_robustness_audit_artifact(
    protocol: FlagshipStudyProtocol,
    anchor: ConfirmatoryRobustnessAnchor,
    regimes: tuple[RobustnessRegimeExperiments, ...],
    *,
    source_git_commit: str,
    confidence_level: float = 0.95,
) -> RobustnessAuditArtifact:
    """Build estimation-only audits for all prespecified robustness regimes."""

    if not math.isfinite(confidence_level) or not 0.0 < confidence_level < 1.0:
        raise StudyProtocolError("robustness confidence_level must be in (0, 1)")
    verify_robustness_experiments(protocol, anchor, regimes)

    references = anchor.primary_effect_map()
    regime_contracts = {item.regime_id: item for item in protocol.robustness_regimes}
    metric_names = tuple(item.metric_name for item in protocol.outcomes)
    output: list[RobustnessRegimeAudit] = []

    for regime in regimes:
        inference = infer_narrative_stability_sweep(
            regime.experiments,
            metric_names=metric_names,
            control_homogeneity=protocol.control_homogeneity,
            confidence_level=confidence_level,
        )
        by_metric = {item.metric_name: item for item in inference}
        outcomes = tuple(
            _outcome_audit(
                outcome.role,
                outcome.metric_name,
                by_metric[outcome.metric_name].contrasts,
                (references[outcome.metric_name] if outcome.role is OutcomeRole.PRIMARY else None),
            )
            for outcome in protocol.outcomes
        )
        contract = regime_contracts[regime.regime_id]
        output.append(
            RobustnessRegimeAudit(
                regime_id=contract.regime_id,
                parameter_name=contract.parameter_name,
                parameter_value=contract.parameter_value,
                outcomes=outcomes,
            )
        )

    seeds = robustness_seed_tuple(protocol, anchor.selected_seed_count)
    artifact = RobustnessAuditArtifact(
        artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_fingerprint=protocol.fingerprint,
        source_git_commit=source_git_commit,
        confirmatory_artifact_sha256=anchor.artifact_sha256,
        confirmatory_source_git_commit=anchor.source_git_commit,
        selected_seed_count=anchor.selected_seed_count,
        robustness_seed_namespace=_ROBUSTNESS_SEED_NAMESPACE,
        robustness_seed_count=len(seeds),
        robustness_seed_fingerprint=_seed_fingerprint(seeds),
        pilot_seed_overlap_count=len(set(seeds).intersection(precision_pilot_seed_tuple(protocol))),
        confirmatory_seed_overlap_count=len(
            set(seeds).intersection(confirmatory_seed_tuple(protocol, anchor.selected_seed_count))
        ),
        confidence_level=confidence_level,
        interval_scope=_INTERVAL_SCOPE,
        inference_scope=_INFERENCE_SCOPE,
        regimes=tuple(output),
    )
    return artifact


def write_robustness_audit_artifact(
    artifact: RobustnessAuditArtifact,
    path: str | os.PathLike[str],
) -> str:
    """Write canonical robustness JSON exactly once."""

    if not isinstance(artifact, RobustnessAuditArtifact):
        raise TypeError("artifact must be a RobustnessAuditArtifact")
    target = Path(path)
    if target.exists():
        raise StudyProtocolError(f"robustness artifact already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    if temporary.exists():
        raise StudyProtocolError(f"robustness temporary artifact already exists: {temporary}")
    temporary.write_bytes(artifact.canonical_bytes)
    os.replace(temporary, target)
    return artifact.sha256


def run_flagship_robustness_audit(
    *,
    confirmatory_artifact_path: str | os.PathLike[str],
    source_git_commit: str,
    expected_confirmatory_sha256: str = (OFFICIAL_FLAGSHIP_CONFIRMATORY_ARTIFACT_SHA256),
) -> RobustnessAuditArtifact:
    """Run all eight frozen regimes using one fresh shared CRN seed tuple."""

    protocol = flagship_narrative_stability_protocol()
    verify_bundled_flagship_protocol(protocol)
    anchor = load_confirmatory_robustness_anchor(
        confirmatory_artifact_path,
        protocol,
        expected_sha256=expected_confirmatory_sha256,
    )
    seeds = robustness_seed_tuple(protocol, anchor.selected_seed_count)
    regimes = tuple(
        RobustnessRegimeExperiments(
            regime_id=regime.regime_id,
            experiments=run_narrative_stability_homogeneity_sweep(
                apply_robustness_regime(protocol, regime.regime_id),
                homogeneities=protocol.homogeneities,
                seeds=seeds,
            ),
        )
        for regime in protocol.robustness_regimes
    )
    return build_robustness_audit_artifact(
        protocol,
        anchor,
        regimes,
        source_git_commit=source_git_commit,
    )
