"""Baseline market calibration and replication API."""

from abmforge_finance.calibration.baseline import (
    CalibrationExperimentResult,
    ConstantFundamentalBenchmarkConfig,
    run_constant_fundamental_benchmark,
    run_passive_depth_sweep,
)
from abmforge_finance.calibration.contracts import (
    CalibrationRunSpec,
    CalibrationScenario,
    validate_seed_tuple,
)
from abmforge_finance.calibration.result import (
    CalibrationRunResult,
    evaluate_calibration_dataset,
)
from abmforge_finance.calibration.runner import (
    DatasetFactory,
    run_and_summarize_calibration,
    run_calibration_replicates,
)
from abmforge_finance.calibration.summary import (
    CalibrationMetricSummary,
    CalibrationSummary,
    summarize_calibration_runs,
)

__all__ = [
    "CalibrationExperimentResult",
    "CalibrationMetricSummary",
    "CalibrationRunResult",
    "CalibrationRunSpec",
    "CalibrationScenario",
    "CalibrationSummary",
    "ConstantFundamentalBenchmarkConfig",
    "DatasetFactory",
    "evaluate_calibration_dataset",
    "run_and_summarize_calibration",
    "run_calibration_replicates",
    "run_constant_fundamental_benchmark",
    "run_passive_depth_sweep",
    "summarize_calibration_runs",
    "validate_seed_tuple",
]
