"""Public API tests for calibration package."""

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    CalibrationMetricSummary,
    CalibrationRunResult,
    CalibrationRunSpec,
    CalibrationScenario,
    CalibrationSummary,
    ConstantFundamentalBenchmarkConfig,
    evaluate_calibration_dataset,
    run_and_summarize_calibration,
    run_calibration_replicates,
    run_constant_fundamental_benchmark,
    run_passive_depth_sweep,
    summarize_calibration_runs,
)


def test_calibration_public_api() -> None:
    assert CalibrationScenario.__name__ == "CalibrationScenario"
    assert CalibrationRunSpec.__name__ == "CalibrationRunSpec"
    assert CalibrationRunResult.__name__ == "CalibrationRunResult"
    assert CalibrationMetricSummary.__name__ == "CalibrationMetricSummary"
    assert CalibrationSummary.__name__ == "CalibrationSummary"
    assert CalibrationExperimentResult.__name__ == "CalibrationExperimentResult"
    assert ConstantFundamentalBenchmarkConfig.__name__ == ("ConstantFundamentalBenchmarkConfig")
    assert callable(evaluate_calibration_dataset)
    assert callable(run_calibration_replicates)
    assert callable(run_and_summarize_calibration)
    assert callable(summarize_calibration_runs)
    assert callable(run_constant_fundamental_benchmark)
    assert callable(run_passive_depth_sweep)
