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
from abmforge_finance.calibration.inference import (
    ContrastRegionSummary,
    PairedTreatmentContrast,
    paired_treatment_contrast,
    student_t_critical_value,
    summarize_contrast_region,
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
from abmforge_finance.calibration.sweeps import (
    run_noise_activity_sweep,
    run_noise_population_sweep,
    run_quote_width_sweep,
)
from abmforge_finance.calibration.tracking import (
    FundamentalTrackingBenchmarkConfig,
    run_fundamental_tracking_benchmark,
)

__all__ = [
    "CalibrationExperimentResult",
    "CalibrationMetricSummary",
    "CalibrationRunResult",
    "CalibrationRunSpec",
    "CalibrationScenario",
    "CalibrationSummary",
    "ConstantFundamentalBenchmarkConfig",
    "ContrastRegionSummary",
    "DatasetFactory",
    "FundamentalTrackingBenchmarkConfig",
    "PairedTreatmentContrast",
    "evaluate_calibration_dataset",
    "paired_treatment_contrast",
    "run_and_summarize_calibration",
    "run_calibration_replicates",
    "run_constant_fundamental_benchmark",
    "run_fundamental_tracking_benchmark",
    "run_noise_activity_sweep",
    "run_noise_population_sweep",
    "run_passive_depth_sweep",
    "run_quote_width_sweep",
    "student_t_critical_value",
    "summarize_calibration_runs",
    "summarize_contrast_region",
    "validate_seed_tuple",
]
