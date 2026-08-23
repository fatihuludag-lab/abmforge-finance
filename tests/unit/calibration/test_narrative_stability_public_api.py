"""Public API tests for Phase 10C.2 narrative-stability calibration."""

from abmforge_finance import calibration


def test_narrative_stability_calibration_api_is_exported() -> None:
    for name in (
        "NarrativeStabilityBenchmarkConfig",
        "NarrativeStabilityMetricInference",
        "NarrativeStabilityRunResult",
        "evaluate_narrative_stability_run",
        "infer_narrative_stability_sweep",
        "run_narrative_stability_benchmark",
        "run_narrative_stability_homogeneity_sweep",
    ):
        assert hasattr(calibration, name)
