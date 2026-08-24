"""Public API test for the Phase 11A stylized-validation contract."""

from abmforge_finance import study


def test_stylized_validation_public_api() -> None:
    expected = (
        "ConcordanceClass",
        "StylizedFactExpectation",
        "StylizedFactRole",
        "StylizedFactSpec",
        "StylizedValidationProtocol",
        "build_stylized_validation_benchmark_config",
        "bundled_stylized_validation_protocol_mapping",
        "stylized_fact_validation_protocol",
        "stylized_validation_seed_tuple",
        "verify_bundled_stylized_validation_protocol",
    )
    for name in expected:
        assert name in study.__all__
        assert hasattr(study, name)
