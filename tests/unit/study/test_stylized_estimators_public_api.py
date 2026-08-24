"""Public API tests for shared Phase 11 market-signature estimators."""

from abmforge_finance import study


def test_shared_market_signature_estimators_are_public() -> None:
    expected = (
        "AbsoluteReturnAutocorrelationEstimate",
        "AggressorSignAutocorrelationEstimate",
        "DepthConditionedImpactEstimate",
        "LiquidityFragilityEstimate",
        "MarketSignatureEstimates",
        "OlsEstimate",
        "ReturnAutocorrelationEstimate",
        "ReturnTailShapeEstimate",
        "estimate_absolute_log_return_acf",
        "estimate_aggressor_flow_price_impact_ols",
        "estimate_aggressor_sign_acf",
        "estimate_depth_conditioned_aggressor_flow_impact_ols",
        "estimate_liquidity_fragility_spearman",
        "estimate_log_return_acf",
        "estimate_market_signatures",
        "estimate_return_tail_shape",
    )

    for name in expected:
        assert name in study.__all__
        assert hasattr(study, name)
