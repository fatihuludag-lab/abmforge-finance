"""Paired treatment contrasts and uncertainty for calibration experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass

from abmforge_finance.calibration.baseline import CalibrationExperimentResult
from abmforge_finance.calibration.contracts import CalibrationScenario
from abmforge_finance.calibration.result import CalibrationRunResult
from abmforge_finance.exceptions import CalibrationInferenceError

_BETA_MAX_ITERATIONS = 200
_BETA_EPSILON = 3e-14
_BETA_FLOOR = 1e-300
_QUANTILE_ITERATIONS = 120


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CalibrationInferenceError(f"{field_name} must be a positive integer")
    return value


def _confidence_level(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationInferenceError("confidence_level must be a real number")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0 or converted >= 1.0:
        raise CalibrationInferenceError("confidence_level must be strictly between 0 and 1")
    return converted


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Evaluate the incomplete-beta continued fraction deterministically."""

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0

    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _BETA_FLOOR:
        d = _BETA_FLOOR
    d = 1.0 / d
    h = d

    for iteration in range(1, _BETA_MAX_ITERATIONS + 1):
        doubled = 2 * iteration
        aa = iteration * (b - iteration) * x / ((qam + doubled) * (a + doubled))
        d = 1.0 + aa * d
        if abs(d) < _BETA_FLOOR:
            d = _BETA_FLOOR
        c = 1.0 + aa / c
        if abs(c) < _BETA_FLOOR:
            c = _BETA_FLOOR
        d = 1.0 / d
        h *= d * c

        aa = -(a + iteration) * (qab + iteration) * x / ((a + doubled) * (qap + doubled))
        d = 1.0 + aa * d
        if abs(d) < _BETA_FLOOR:
            d = _BETA_FLOOR
        c = 1.0 + aa / c
        if abs(c) < _BETA_FLOOR:
            c = _BETA_FLOOR
        d = 1.0 / d
        delta = d * c
        h *= delta

        if abs(delta - 1.0) < _BETA_EPSILON:
            return h

    raise CalibrationInferenceError("regularized incomplete-beta evaluation did not converge")


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    log_beta_term = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    beta_term = math.exp(log_beta_term)

    if x < (a + 1.0) / (a + b + 2.0):
        return beta_term * _beta_continued_fraction(a, b, x) / a
    return 1.0 - beta_term * _beta_continued_fraction(b, a, 1.0 - x) / b


def _student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    df = float(degrees_of_freedom)
    x = df / (df + value * value)
    incomplete = _regularized_incomplete_beta(df / 2.0, 0.5, x)
    if value >= 0.0:
        return 1.0 - 0.5 * incomplete
    return 0.5 * incomplete


def student_t_critical_value(
    degrees_of_freedom: int,
    *,
    confidence_level: float = 0.95,
) -> float:
    """Return the positive two-sided Student-t critical value.

    The implementation evaluates the Student-t CDF through the regularized
    incomplete-beta representation and inverts it with deterministic bisection.
    No external statistical runtime dependency is required.
    """

    df = _positive_int(degrees_of_freedom, field_name="degrees_of_freedom")
    level = _confidence_level(confidence_level)
    target = 0.5 + level / 2.0

    lower = 0.0
    upper = 1.0
    while _student_t_cdf(upper, df) < target:
        upper *= 2.0
        if not math.isfinite(upper) or upper > 1e12:
            raise CalibrationInferenceError(
                "Student-t quantile bracketing failed for the requested confidence level"
            )

    for _ in range(_QUANTILE_ITERATIONS):
        midpoint = (lower + upper) / 2.0
        if _student_t_cdf(midpoint, df) < target:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


@dataclass(frozen=True, slots=True)
class PairedTreatmentContrast:
    """Seed-paired treatment-minus-control contrast for one metric."""

    metric_name: str
    control_scenario: CalibrationScenario
    treatment_scenario: CalibrationScenario
    changed_parameters: tuple[tuple[str, str, str], ...]
    seeds: tuple[int, ...]
    differences: tuple[float, ...]
    mean_difference: float
    sample_std_difference: float
    standard_error: float
    confidence_level: float
    critical_value: float
    confidence_interval_lower: float
    confidence_interval_upper: float

    @property
    def pair_count(self) -> int:
        return len(self.seeds)

    @property
    def excludes_zero(self) -> bool:
        return self.confidence_interval_lower > 0.0 or self.confidence_interval_upper < 0.0


@dataclass(frozen=True, slots=True)
class ContrastRegionSummary:
    """Descriptive directional consistency across related paired contrasts."""

    metric_name: str
    control_scenario: CalibrationScenario
    confidence_level: float
    contrast_count: int
    positive_mean_count: int
    negative_mean_count: int
    zero_mean_count: int
    intervals_excluding_zero_count: int
    direction_consistency: str
    minimum_mean_difference: float
    maximum_mean_difference: float


def _validate_experiment(
    experiment: CalibrationExperimentResult,
    *,
    label: str,
) -> tuple[int, ...]:
    if not isinstance(experiment, CalibrationExperimentResult):
        raise TypeError(f"{label} must be a CalibrationExperimentResult")
    if not experiment.runs:
        raise CalibrationInferenceError(f"{label} must contain at least one replicate")
    if experiment.summary.scenario != experiment.scenario:
        raise CalibrationInferenceError(
            f"{label} summary scenario does not match the experiment scenario"
        )
    if any(run.spec.scenario != experiment.scenario for run in experiment.runs):
        raise CalibrationInferenceError(
            f"{label} replicate scenario does not match the experiment scenario"
        )

    replicates = tuple(run.spec.replicate for run in experiment.runs)
    if replicates != tuple(range(len(experiment.runs))):
        raise CalibrationInferenceError(f"{label} replicates must be contiguous and zero-based")

    seeds = tuple(run.spec.seed for run in experiment.runs)
    if seeds != experiment.summary.seeds:
        raise CalibrationInferenceError(
            f"{label} replicate seeds do not match its summary seed tuple"
        )
    return seeds


def _changed_parameters(
    control: CalibrationScenario,
    treatment: CalibrationScenario,
) -> tuple[tuple[str, str, str], ...]:
    if control.scenario_id != treatment.scenario_id:
        raise CalibrationInferenceError("paired treatments must share the same scenario_id")
    if control.periods != treatment.periods:
        raise CalibrationInferenceError("paired treatments must share the same simulation horizon")
    if control.treatment_id == treatment.treatment_id:
        raise CalibrationInferenceError(
            "control and treatment must have distinct treatment_id values"
        )

    control_parameters = dict(control.parameters)
    treatment_parameters = dict(treatment.parameters)
    if tuple(control_parameters) != tuple(treatment_parameters):
        raise CalibrationInferenceError("paired treatments must expose identical parameter keys")

    changed = tuple(
        (key, control_parameters[key], treatment_parameters[key])
        for key in control_parameters
        if control_parameters[key] != treatment_parameters[key]
    )
    if not changed:
        raise CalibrationInferenceError(
            "paired treatments must differ in at least one canonical parameter"
        )
    return changed


def _metric_value(run: CalibrationRunResult, metric_name: str) -> float:
    metrics = dict(run.metric_items())
    if metric_name not in metrics:
        raise CalibrationInferenceError(f"unknown calibration metric {metric_name!r}")
    value = metrics[metric_name]
    if value is None:
        raise CalibrationInferenceError(
            f"metric {metric_name!r} is undefined for seed {run.spec.seed}"
        )
    converted = float(value)
    if not math.isfinite(converted):
        raise CalibrationInferenceError(
            f"metric {metric_name!r} must be finite for seed {run.spec.seed}"
        )
    return converted


def paired_treatment_contrast(
    control: CalibrationExperimentResult,
    treatment: CalibrationExperimentResult,
    *,
    metric_name: str,
    confidence_level: float = 0.95,
) -> PairedTreatmentContrast:
    """Compute a Student-t CI for seed-paired treatment-minus-control differences."""

    if not isinstance(metric_name, str) or not metric_name.strip():
        raise CalibrationInferenceError("metric_name must be a non-empty string")
    level = _confidence_level(confidence_level)

    control_seeds = _validate_experiment(control, label="control")
    treatment_seeds = _validate_experiment(treatment, label="treatment")
    if control_seeds != treatment_seeds:
        raise CalibrationInferenceError(
            "paired treatment contrasts require identical ordered seed tuples"
        )
    if len(control_seeds) < 2:
        raise CalibrationInferenceError(
            "paired treatment contrasts require at least two replicate pairs"
        )

    changed = _changed_parameters(control.scenario, treatment.scenario)

    differences = tuple(
        _metric_value(treatment_run, metric_name) - _metric_value(control_run, metric_name)
        for control_run, treatment_run in zip(
            control.runs,
            treatment.runs,
            strict=True,
        )
    )

    count = len(differences)
    mean_difference = sum(differences) / count
    variance = sum((difference - mean_difference) ** 2 for difference in differences) / (count - 1)
    sample_std = math.sqrt(variance)
    standard_error = sample_std / math.sqrt(count)
    critical = student_t_critical_value(
        count - 1,
        confidence_level=level,
    )
    margin = critical * standard_error

    return PairedTreatmentContrast(
        metric_name=metric_name.strip(),
        control_scenario=control.scenario,
        treatment_scenario=treatment.scenario,
        changed_parameters=changed,
        seeds=control_seeds,
        differences=differences,
        mean_difference=mean_difference,
        sample_std_difference=sample_std,
        standard_error=standard_error,
        confidence_level=level,
        critical_value=critical,
        confidence_interval_lower=mean_difference - margin,
        confidence_interval_upper=mean_difference + margin,
    )


def summarize_contrast_region(
    contrasts: tuple[PairedTreatmentContrast, ...],
) -> ContrastRegionSummary:
    """Summarize effect-direction consistency across a related treatment region.

    This function is descriptive only. It does not adjust confidence intervals for
    multiple comparisons and must not be interpreted as family-wise inference.
    """

    if not isinstance(contrasts, tuple) or not contrasts:
        raise CalibrationInferenceError("contrasts must be a non-empty tuple")
    if not all(isinstance(item, PairedTreatmentContrast) for item in contrasts):
        raise CalibrationInferenceError("contrasts must contain PairedTreatmentContrast values")

    first = contrasts[0]
    if any(item.metric_name != first.metric_name for item in contrasts):
        raise CalibrationInferenceError("all contrasts must use the same metric")
    if any(item.control_scenario != first.control_scenario for item in contrasts):
        raise CalibrationInferenceError("all contrasts must share one control scenario")
    if any(item.confidence_level != first.confidence_level for item in contrasts):
        raise CalibrationInferenceError("all contrasts must use the same confidence level")

    treatment_ids = tuple(item.treatment_scenario.treatment_id for item in contrasts)
    if len(set(treatment_ids)) != len(treatment_ids):
        raise CalibrationInferenceError("contrast region treatment_id values must be unique")

    means = tuple(item.mean_difference for item in contrasts)
    positive = sum(value > 0.0 for value in means)
    negative = sum(value < 0.0 for value in means)
    zero = len(means) - positive - negative

    if positive == len(means):
        direction = "positive"
    elif negative == len(means):
        direction = "negative"
    elif zero == len(means):
        direction = "zero"
    else:
        direction = "mixed"

    return ContrastRegionSummary(
        metric_name=first.metric_name,
        control_scenario=first.control_scenario,
        confidence_level=first.confidence_level,
        contrast_count=len(contrasts),
        positive_mean_count=positive,
        negative_mean_count=negative,
        zero_mean_count=zero,
        intervals_excluding_zero_count=sum(item.excludes_zero for item in contrasts),
        direction_consistency=direction,
        minimum_mean_difference=min(means),
        maximum_mean_difference=max(means),
    )
