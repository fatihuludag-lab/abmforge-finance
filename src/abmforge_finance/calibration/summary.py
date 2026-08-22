"""Descriptive multi-replicate summaries for calibration experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.calibration.contracts import CalibrationScenario
from abmforge_finance.calibration.result import CalibrationRunResult
from abmforge_finance.exceptions import InvalidCalibrationError


@dataclass(frozen=True, slots=True)
class CalibrationMetricSummary:
    """Descriptive summary of one metric across defined replicate values."""

    metric_name: str
    total_replicates: int
    defined_replicates: int
    mean: float | None
    sample_std: float | None
    standard_error: float | None
    minimum: float | None
    maximum: float | None


@dataclass(frozen=True, slots=True)
class CalibrationSummary:
    """Treatment-level descriptive summary with explicit seeds and fingerprint."""

    scenario: CalibrationScenario
    seeds: tuple[int, ...]
    metrics: tuple[CalibrationMetricSummary, ...]

    @property
    def replicate_count(self) -> int:
        return len(self.seeds)

    def metric(self, name: str) -> CalibrationMetricSummary:
        """Return a named metric summary or fail explicitly."""

        for metric in self.metrics:
            if metric.metric_name == name:
                return metric
        raise KeyError(name)


def _float_value(value: int | float | Decimal | None) -> float | None:
    if value is None:
        return None
    converted = float(value)
    if not math.isfinite(converted):
        raise InvalidCalibrationError("calibration metrics must be finite when defined")
    return converted


def _summarize(
    name: str,
    values: tuple[int | float | Decimal | None, ...],
) -> CalibrationMetricSummary:
    defined = tuple(converted for value in values if (converted := _float_value(value)) is not None)
    total = len(values)
    count = len(defined)
    if count == 0:
        return CalibrationMetricSummary(name, total, 0, None, None, None, None, None)

    mean = sum(defined) / count
    if count == 1:
        sample_std = None
        standard_error = None
    else:
        variance = sum((value - mean) ** 2 for value in defined) / (count - 1)
        sample_std = math.sqrt(variance)
        standard_error = sample_std / math.sqrt(count)

    return CalibrationMetricSummary(
        metric_name=name,
        total_replicates=total,
        defined_replicates=count,
        mean=mean,
        sample_std=sample_std,
        standard_error=standard_error,
        minimum=min(defined),
        maximum=max(defined),
    )


def summarize_calibration_runs(
    runs: tuple[CalibrationRunResult, ...],
) -> CalibrationSummary:
    """Summarize replicates from exactly one canonical scenario/treatment."""

    if not isinstance(runs, tuple) or not runs:
        raise InvalidCalibrationError("runs must be a non-empty tuple")
    if not all(isinstance(run, CalibrationRunResult) for run in runs):
        raise InvalidCalibrationError("runs must contain CalibrationRunResult values")

    scenario = runs[0].spec.scenario
    if any(run.spec.scenario != scenario for run in runs):
        raise InvalidCalibrationError(
            "all summarized runs must share one canonical scenario/treatment"
        )
    replicates = tuple(run.spec.replicate for run in runs)
    if replicates != tuple(range(len(runs))):
        raise InvalidCalibrationError(
            "runs must be ordered by contiguous zero-based replicate index"
        )
    seeds = tuple(run.spec.seed for run in runs)
    if len(set(seeds)) != len(seeds):
        raise InvalidCalibrationError("summarized run seeds must be unique")

    metric_names = tuple(name for name, _ in runs[0].metric_items())
    for run in runs[1:]:
        if tuple(name for name, _ in run.metric_items()) != metric_names:
            raise InvalidCalibrationError("replicate metric schemas do not match")

    summaries = tuple(
        _summarize(
            name,
            tuple(dict(run.metric_items())[name] for run in runs),
        )
        for name in metric_names
    )
    return CalibrationSummary(
        scenario=scenario,
        seeds=seeds,
        metrics=summaries,
    )
