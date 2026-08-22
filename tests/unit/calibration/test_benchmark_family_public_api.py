"""Public API tests for Phase 9C.2 benchmark families."""

from abmforge_finance.calibration import (
    FundamentalTrackingBenchmarkConfig,
    run_fundamental_tracking_benchmark,
    run_noise_activity_sweep,
    run_noise_population_sweep,
    run_quote_width_sweep,
)


def test_phase9c2_benchmark_public_api() -> None:
    assert FundamentalTrackingBenchmarkConfig.__name__ == ("FundamentalTrackingBenchmarkConfig")
    assert callable(run_fundamental_tracking_benchmark)
    assert callable(run_quote_width_sweep)
    assert callable(run_noise_activity_sweep)
    assert callable(run_noise_population_sweep)
