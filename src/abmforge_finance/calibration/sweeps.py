"""Common-random-number benchmark treatment sweeps."""

from __future__ import annotations

from dataclasses import replace

from abmforge_finance.calibration.baseline import (
    CalibrationExperimentResult,
    ConstantFundamentalBenchmarkConfig,
    run_constant_fundamental_benchmark,
)
from abmforge_finance.exceptions import InvalidCalibrationError


def _non_empty_unique_tuple(value: object, *, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, tuple) or not value:
        raise InvalidCalibrationError(f"{field_name} must be a non-empty tuple")
    if len(set(value)) != len(value):
        raise InvalidCalibrationError(f"{field_name} must be unique")
    return value


def run_quote_width_sweep(
    config: ConstantFundamentalBenchmarkConfig,
    *,
    quote_offset_ticks: tuple[int, ...],
    seeds: tuple[int, ...],
) -> tuple[CalibrationExperimentResult, ...]:
    """Vary quote offset while reusing identical replicate seeds."""

    if not isinstance(config, ConstantFundamentalBenchmarkConfig):
        raise TypeError("config must be a ConstantFundamentalBenchmarkConfig")
    values = _non_empty_unique_tuple(
        quote_offset_ticks,
        field_name="quote_offset_ticks",
    )

    experiments: list[CalibrationExperimentResult] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidCalibrationError("quote_offset_ticks values must be positive integers")
        treatment = replace(
            config,
            quote_offset_ticks=value,
            treatment_id=f"quote-offset-ticks={value}",
        )
        experiments.append(run_constant_fundamental_benchmark(treatment, seeds=seeds))
    return tuple(experiments)


def run_noise_activity_sweep(
    config: ConstantFundamentalBenchmarkConfig,
    *,
    activity_bps: tuple[int, ...],
    seeds: tuple[int, ...],
) -> tuple[CalibrationExperimentResult, ...]:
    """Vary noise activity threshold under common random numbers."""

    if not isinstance(config, ConstantFundamentalBenchmarkConfig):
        raise TypeError("config must be a ConstantFundamentalBenchmarkConfig")
    values = _non_empty_unique_tuple(activity_bps, field_name="activity_bps")

    experiments: list[CalibrationExperimentResult] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10_000:
            raise InvalidCalibrationError("activity_bps values must be integers in [0, 10000]")
        treatment = replace(
            config,
            noise_activity_bps=value,
            treatment_id=f"noise-activity-bps={value}",
        )
        experiments.append(run_constant_fundamental_benchmark(treatment, seeds=seeds))
    return tuple(experiments)


def run_noise_population_sweep(
    config: ConstantFundamentalBenchmarkConfig,
    *,
    noise_trader_counts: tuple[int, ...],
    seeds: tuple[int, ...],
) -> tuple[CalibrationExperimentResult, ...]:
    """Vary noise population while preserving stable prefix agent identities."""

    if not isinstance(config, ConstantFundamentalBenchmarkConfig):
        raise TypeError("config must be a ConstantFundamentalBenchmarkConfig")
    values = _non_empty_unique_tuple(
        noise_trader_counts,
        field_name="noise_trader_counts",
    )

    experiments: list[CalibrationExperimentResult] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidCalibrationError("noise_trader_counts values must be positive integers")
        treatment = replace(
            config,
            noise_trader_count=value,
            treatment_id=f"noise-traders={value}",
        )
        experiments.append(run_constant_fundamental_benchmark(treatment, seeds=seeds))
    return tuple(experiments)
