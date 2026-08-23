"""Public API checks for Phase 10C market-stability symbols."""

import abmforge_finance
from abmforge_finance import experiments, metrics


def test_narrative_market_stability_api_is_exported() -> None:
    for name in (
        "NarrativeDirectionSchedule",
        "NarrativeMarketStabilityOutcome",
        "evaluate_narrative_market_stability",
        "evaluate_narrative_market_stability_sweep",
    ):
        assert getattr(abmforge_finance, name) is getattr(experiments, name)

    assert issubclass(abmforge_finance.InvalidNarrativeStabilityError, Exception)


def test_directional_liquidity_metrics_are_public() -> None:
    for name in (
        "depth_asymmetry",
        "thin_side_depletion",
        "thin_side_depth",
    ):
        assert callable(getattr(metrics, name))
