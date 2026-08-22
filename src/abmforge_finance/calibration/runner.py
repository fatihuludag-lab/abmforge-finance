"""Deterministic multi-seed execution contract for finance calibration."""

from __future__ import annotations

from collections.abc import Callable

from abmforge_finance.calibration.contracts import (
    CalibrationRunSpec,
    CalibrationScenario,
    validate_seed_tuple,
)
from abmforge_finance.calibration.result import (
    CalibrationRunResult,
    evaluate_calibration_dataset,
)
from abmforge_finance.calibration.summary import (
    CalibrationSummary,
    summarize_calibration_runs,
)
from abmforge_finance.exceptions import CalibrationExecutionError
from abmforge_finance.recording import FinanceResearchDataset

DatasetFactory = Callable[[CalibrationRunSpec], FinanceResearchDataset]


def run_calibration_replicates(
    scenario: CalibrationScenario,
    *,
    seeds: tuple[int, ...],
    dataset_factory: DatasetFactory,
) -> tuple[CalibrationRunResult, ...]:
    """Run explicit replicate seeds in supplied order and evaluate each dataset."""

    if not isinstance(scenario, CalibrationScenario):
        raise TypeError("scenario must be a CalibrationScenario")
    validated_seeds = validate_seed_tuple(seeds)
    if not callable(dataset_factory):
        raise TypeError("dataset_factory must be callable")

    results: list[CalibrationRunResult] = []
    for replicate, seed in enumerate(validated_seeds):
        spec = CalibrationRunSpec(
            scenario=scenario,
            replicate=replicate,
            seed=seed,
        )
        dataset = dataset_factory(spec)
        if not isinstance(dataset, FinanceResearchDataset):
            raise CalibrationExecutionError("dataset_factory must return a FinanceResearchDataset")
        results.append(evaluate_calibration_dataset(spec, dataset))
    return tuple(results)


def run_and_summarize_calibration(
    scenario: CalibrationScenario,
    *,
    seeds: tuple[int, ...],
    dataset_factory: DatasetFactory,
) -> tuple[tuple[CalibrationRunResult, ...], CalibrationSummary]:
    """Return replicate-level outcomes and a descriptive treatment summary."""

    runs = run_calibration_replicates(
        scenario,
        seeds=seeds,
        dataset_factory=dataset_factory,
    )
    return runs, summarize_calibration_runs(runs)
