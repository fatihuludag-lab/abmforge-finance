"""Public API tests for the shared Phase 11 preparation pipeline."""

from abmforge_finance import study


def test_shared_market_signature_pipeline_is_public() -> None:
    expected = (
        "EMPIRICAL_MARKET_SIGNATURE_PREPARATION_ID",
        "EmpiricalMarketInterval",
        "MarketSignatureInput",
        "MarketSignatureInputProvenance",
        "MarketSignatureSourceKind",
        "PreparedMarketSignatureSample",
        "SIMULATION_MARKET_SIGNATURE_PREPARATION_ID",
        "estimate_prepared_market_signatures",
        "prepare_empirical_market_signature_sample",
        "prepare_stylized_validation_simulation_sample",
    )

    for name in expected:
        assert name in study.__all__
        assert hasattr(study, name)
