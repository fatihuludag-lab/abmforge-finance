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
from abmforge_finance.calibration.narrative_stability import (
    NarrativeStabilityBenchmarkConfig,
    NarrativeStabilityMetricInference,
    NarrativeStabilityRunResult,
    evaluate_narrative_stability_run,
    infer_narrative_stability_sweep,
    run_narrative_stability_benchmark,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.calibration.result import (
    CalibrationRunResult,
    evaluate_calibration_dataset,
)
from abmforge_finance.calibration.robustness import (
    BaselineEcologyAudit,
    NormalizedSensitivity,
    RobustnessClassification,
    TreatmentFamilyAudit,
    audit_parameter_sweep,
    build_baseline_ecology_audit,
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
    "BaselineEcologyAudit",
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
    "NarrativeStabilityBenchmarkConfig",
    "NarrativeStabilityMetricInference",
    "NarrativeStabilityRunResult",
    "NormalizedSensitivity",
    "PairedTreatmentContrast",
    "RobustnessClassification",
    "TreatmentFamilyAudit",
    "audit_parameter_sweep",
    "build_baseline_ecology_audit",
    "evaluate_calibration_dataset",
    "evaluate_narrative_stability_run",
    "infer_narrative_stability_sweep",
    "paired_treatment_contrast",
    "run_and_summarize_calibration",
    "run_calibration_replicates",
    "run_constant_fundamental_benchmark",
    "run_fundamental_tracking_benchmark",
    "run_narrative_stability_benchmark",
    "run_narrative_stability_homogeneity_sweep",
    "run_noise_activity_sweep",
    "run_noise_population_sweep",
    "run_passive_depth_sweep",
    "run_quote_width_sweep",
    "student_t_critical_value",
    "summarize_calibration_runs",
    "summarize_contrast_region",
    "validate_seed_tuple",
]
