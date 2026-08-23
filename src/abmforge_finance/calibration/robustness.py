"""Robustness and normalized-sensitivity audits for calibration sweeps."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from abmforge_finance.calibration.baseline import CalibrationExperimentResult
from abmforge_finance.calibration.contracts import CalibrationScenario
from abmforge_finance.calibration.inference import (
    ContrastRegionSummary,
    PairedTreatmentContrast,
    paired_treatment_contrast,
    summarize_contrast_region,
)
from abmforge_finance.exceptions import CalibrationRobustnessError


class RobustnessClassification(str, Enum):
    """Directional classification across an explicit treatment region."""

    ROBUST_POSITIVE = "ROBUST_POSITIVE"
    ROBUST_NEGATIVE = "ROBUST_NEGATIVE"
    ROBUST_ZERO = "ROBUST_ZERO"
    MIXED = "MIXED"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class NormalizedSensitivity:
    """Dimensionless local treatment sensitivity when normalization is valid."""

    parameter_name: str
    metric_name: str
    treatment_id: str
    control_parameter_value: str
    treatment_parameter_value: str
    control_metric_mean: float
    treatment_metric_mean: float
    parameter_relative_change: float | None
    metric_relative_change: float | None
    elasticity: float | None
    undefined_reason: str | None

    @property
    def defined(self) -> bool:
        return self.elasticity is not None


@dataclass(frozen=True, slots=True)
class TreatmentFamilyAudit:
    """Robustness audit for one parameter family and one outcome metric."""

    family_name: str
    parameter_name: str
    metric_name: str
    control_scenario: CalibrationScenario
    seeds: tuple[int, ...]
    contrasts: tuple[PairedTreatmentContrast, ...]
    region: ContrastRegionSummary
    classification: RobustnessClassification
    minimum_contrasts: int
    sensitivities: tuple[NormalizedSensitivity, ...]

    @property
    def contrast_count(self) -> int:
        return len(self.contrasts)

    @property
    def all_individual_intervals_exclude_zero(self) -> bool:
        return self.region.intervals_excluding_zero_count == self.region.contrast_count

    @property
    def individual_interval_exclusion_fraction(self) -> float:
        return self.region.intervals_excluding_zero_count / self.region.contrast_count


@dataclass(frozen=True, slots=True)
class BaselineEcologyAudit:
    """Machine-readable aggregation of baseline treatment-family audits.

    Completion means that the requested audit families are present and have enough
    contrasts for their configured directional classification. It is not a certificate
    of empirical realism or external validity.
    """

    audit_id: str
    required_families: tuple[str, ...]
    family_audits: tuple[TreatmentFamilyAudit, ...]
    missing_families: tuple[str, ...]
    insufficient_families: tuple[str, ...]
    mixed_families: tuple[str, ...]
    shared_seed_tuple: tuple[int, ...] | None
    individual_interval_exclusion_count: int
    individual_interval_count: int
    warnings: tuple[str, ...]
    interpretation_note: str

    @property
    def complete(self) -> bool:
        return not self.missing_families and not self.insufficient_families


def _non_empty_name(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationRobustnessError(f"{field_name} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CalibrationRobustnessError(f"{field_name} must be a positive integer")
    return value


def _metric_mean(
    experiment: CalibrationExperimentResult,
    metric_name: str,
) -> float:
    values: list[float] = []
    for run in experiment.runs:
        metrics = dict(run.metric_items())
        if metric_name not in metrics:
            raise CalibrationRobustnessError(f"unknown calibration metric {metric_name!r}")
        value = metrics[metric_name]
        if value is None:
            raise CalibrationRobustnessError(
                f"metric {metric_name!r} is undefined for seed {run.spec.seed}"
            )
        converted = float(value)
        if not math.isfinite(converted):
            raise CalibrationRobustnessError(
                f"metric {metric_name!r} must be finite for seed {run.spec.seed}"
            )
        values.append(converted)
    if not values:
        raise CalibrationRobustnessError("treatment-family experiments must contain replicates")
    return sum(values) / len(values)


def _numeric_parameter(value: str) -> float | None:
    try:
        converted = float(value)
    except ValueError:
        return None
    if not math.isfinite(converted):
        return None
    return converted


def _normalized_sensitivity(
    control: CalibrationExperimentResult,
    treatment: CalibrationExperimentResult,
    contrast: PairedTreatmentContrast,
    *,
    parameter_name: str,
) -> NormalizedSensitivity:
    changed = contrast.changed_parameters
    if len(changed) != 1 or changed[0][0] != parameter_name:
        raise CalibrationRobustnessError(
            "normalized sensitivity requires exactly one changed canonical parameter "
            f"named {parameter_name!r}"
        )

    _, control_parameter_text, treatment_parameter_text = changed[0]
    control_metric_mean = _metric_mean(control, contrast.metric_name)
    treatment_metric_mean = _metric_mean(treatment, contrast.metric_name)

    control_parameter = _numeric_parameter(control_parameter_text)
    treatment_parameter = _numeric_parameter(treatment_parameter_text)

    reason: str | None = None
    parameter_relative_change: float | None = None
    metric_relative_change: float | None = None
    elasticity: float | None = None

    if control_parameter is None or treatment_parameter is None:
        reason = "non_numeric_parameter"
    elif control_parameter == 0.0:
        reason = "zero_control_parameter"
    elif control_metric_mean == 0.0:
        reason = "zero_control_metric"
    else:
        parameter_relative_change = (treatment_parameter - control_parameter) / control_parameter
        if parameter_relative_change == 0.0:
            reason = "zero_numeric_parameter_change"
        else:
            metric_relative_change = (
                treatment_metric_mean - control_metric_mean
            ) / control_metric_mean
            elasticity = metric_relative_change / parameter_relative_change

    return NormalizedSensitivity(
        parameter_name=parameter_name,
        metric_name=contrast.metric_name,
        treatment_id=treatment.scenario.treatment_id,
        control_parameter_value=control_parameter_text,
        treatment_parameter_value=treatment_parameter_text,
        control_metric_mean=control_metric_mean,
        treatment_metric_mean=treatment_metric_mean,
        parameter_relative_change=parameter_relative_change,
        metric_relative_change=metric_relative_change,
        elasticity=elasticity,
        undefined_reason=reason,
    )


def _classification(
    region: ContrastRegionSummary,
    *,
    minimum_contrasts: int,
) -> RobustnessClassification:
    if region.contrast_count < minimum_contrasts:
        return RobustnessClassification.INSUFFICIENT
    if region.direction_consistency == "positive":
        return RobustnessClassification.ROBUST_POSITIVE
    if region.direction_consistency == "negative":
        return RobustnessClassification.ROBUST_NEGATIVE
    if region.direction_consistency == "zero":
        return RobustnessClassification.ROBUST_ZERO
    return RobustnessClassification.MIXED


def audit_parameter_sweep(
    experiments: tuple[CalibrationExperimentResult, ...],
    *,
    control_index: int,
    family_name: str,
    parameter_name: str,
    metric_name: str,
    confidence_level: float = 0.95,
    minimum_contrasts: int = 2,
) -> TreatmentFamilyAudit:
    """Audit one single-parameter sweep using common-seed paired contrasts.

    ``ROBUST_*`` means directional consistency across at least
    ``minimum_contrasts`` explicit treatment points. It does not mean statistical
    significance, simultaneous coverage, empirical realism, or external validity.
    """

    family = _non_empty_name(family_name, field_name="family_name")
    parameter = _non_empty_name(parameter_name, field_name="parameter_name")
    metric = _non_empty_name(metric_name, field_name="metric_name")
    minimum = _positive_int(minimum_contrasts, field_name="minimum_contrasts")

    if not isinstance(experiments, tuple) or len(experiments) < 2:
        raise CalibrationRobustnessError(
            "experiments must be a tuple containing a control and at least one treatment"
        )
    if not all(isinstance(item, CalibrationExperimentResult) for item in experiments):
        raise CalibrationRobustnessError(
            "experiments must contain CalibrationExperimentResult values"
        )
    if (
        isinstance(control_index, bool)
        or not isinstance(control_index, int)
        or control_index < 0
        or control_index >= len(experiments)
    ):
        raise CalibrationRobustnessError(
            "control_index must identify an experiment in the supplied tuple"
        )

    control = experiments[control_index]
    treatment_pairs = tuple(
        (index, experiment)
        for index, experiment in enumerate(experiments)
        if index != control_index
    )

    contrasts: list[PairedTreatmentContrast] = []
    sensitivities: list[NormalizedSensitivity] = []
    for _, treatment in treatment_pairs:
        contrast = paired_treatment_contrast(
            control,
            treatment,
            metric_name=metric,
            confidence_level=confidence_level,
        )
        if len(contrast.changed_parameters) != 1:
            raise CalibrationRobustnessError(
                "parameter-sweep audits require exactly one changed canonical parameter"
            )
        if contrast.changed_parameters[0][0] != parameter:
            raise CalibrationRobustnessError(
                "parameter-sweep changed parameter does not match parameter_name"
            )
        contrasts.append(contrast)
        sensitivities.append(
            _normalized_sensitivity(
                control,
                treatment,
                contrast,
                parameter_name=parameter,
            )
        )

    contrast_tuple = tuple(contrasts)
    region = summarize_contrast_region(contrast_tuple)
    return TreatmentFamilyAudit(
        family_name=family,
        parameter_name=parameter,
        metric_name=metric,
        control_scenario=control.scenario,
        seeds=control.summary.seeds,
        contrasts=contrast_tuple,
        region=region,
        classification=_classification(
            region,
            minimum_contrasts=minimum,
        ),
        minimum_contrasts=minimum,
        sensitivities=tuple(sensitivities),
    )


def build_baseline_ecology_audit(
    family_audits: tuple[TreatmentFamilyAudit, ...],
    *,
    required_families: tuple[str, ...],
    audit_id: str = "baseline-ecology",
) -> BaselineEcologyAudit:
    """Aggregate explicit family audits without converting them into a realism claim."""

    identifier = _non_empty_name(audit_id, field_name="audit_id")
    if not isinstance(family_audits, tuple) or not family_audits:
        raise CalibrationRobustnessError("family_audits must be a non-empty tuple")
    if not all(isinstance(item, TreatmentFamilyAudit) for item in family_audits):
        raise CalibrationRobustnessError("family_audits must contain TreatmentFamilyAudit values")
    if not isinstance(required_families, tuple) or not required_families:
        raise CalibrationRobustnessError("required_families must be a non-empty tuple")

    required = tuple(
        _non_empty_name(value, field_name="required_family") for value in required_families
    )
    if len(set(required)) != len(required):
        raise CalibrationRobustnessError("required_families must be unique")

    family_names = tuple(item.family_name for item in family_audits)
    if len(set(family_names)) != len(family_names):
        raise CalibrationRobustnessError("family audit names must be unique")

    available = set(family_names)
    missing = tuple(name for name in required if name not in available)
    insufficient = tuple(
        item.family_name
        for item in family_audits
        if item.classification is RobustnessClassification.INSUFFICIENT
    )
    mixed = tuple(
        item.family_name
        for item in family_audits
        if item.classification is RobustnessClassification.MIXED
    )

    first_seeds = family_audits[0].seeds
    shared_seeds = first_seeds if all(item.seeds == first_seeds for item in family_audits) else None

    interval_count = sum(item.contrast_count for item in family_audits)
    exclusion_count = sum(item.region.intervals_excluding_zero_count for item in family_audits)

    warnings: list[str] = []
    if missing:
        warnings.append("required treatment families are missing from the baseline ecology audit")
    if insufficient:
        warnings.append(
            "one or more treatment families have fewer than their configured minimum contrast count"
        )
    if shared_seeds is None:
        warnings.append(
            "treatment families use different replicate seed tuples; "
            "cross-family comparisons are not common-seed paired"
        )

    return BaselineEcologyAudit(
        audit_id=identifier,
        required_families=required,
        family_audits=family_audits,
        missing_families=missing,
        insufficient_families=insufficient,
        mixed_families=mixed,
        shared_seed_tuple=shared_seeds,
        individual_interval_exclusion_count=exclusion_count,
        individual_interval_count=interval_count,
        warnings=tuple(warnings),
        interpretation_note=(
            "Directional robustness is distinct from statistical significance; "
            "individual confidence intervals are not simultaneous inference, and "
            "audit completion is not a certificate of empirical realism."
        ),
    )
