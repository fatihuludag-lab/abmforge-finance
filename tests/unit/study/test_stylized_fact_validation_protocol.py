"""Tests for the frozen Phase 11A stylized-fact validation protocol."""

from decimal import Decimal

from abmforge_finance.domain import NarrativeDirection
from abmforge_finance.study import (
    ConcordanceClass,
    StylizedFactExpectation,
    StylizedFactRole,
    build_stylized_validation_benchmark_config,
    bundled_stylized_validation_protocol_mapping,
    flagship_narrative_stability_protocol,
    stylized_fact_validation_protocol,
    stylized_validation_seed_tuple,
    verify_bundled_stylized_validation_protocol,
)


def test_stylized_validation_protocol_contract() -> None:
    protocol = stylized_fact_validation_protocol()

    assert protocol.protocol_id == "stylized-fact-validation-v1"
    assert protocol.protocol_version == "1.0.0"
    assert protocol.validation_homogeneity == Decimal("0")
    assert protocol.burn_in_periods == 256
    assert protocol.analysis_horizon == 4096
    assert protocol.total_periods == 4352
    assert protocol.replicate_count == 16
    assert protocol.maximum_acf_lag == 20
    assert protocol.price_basis == "mid"
    assert protocol.return_type == "log"
    assert protocol.empirical_reference_lower_quantile == Decimal("0.05")
    assert protocol.empirical_reference_upper_quantile == Decimal("0.95")
    assert protocol.model_calibration_permitted is False

    assert protocol.primary_fact_ids == ("SF-04", "SF-05", "SF-06")
    assert protocol.diagnostic_fact_ids == (
        "SF-01",
        "SF-02",
        "SF-03",
        "SF-07",
    )
    assert protocol.classification_values == tuple(item.value for item in ConcordanceClass)


def test_stylized_validation_fact_semantics_are_frozen() -> None:
    protocol = stylized_fact_validation_protocol()
    facts = {item.fact_id: item for item in protocol.facts}

    assert facts["SF-04"].role is StylizedFactRole.PRIMARY
    assert facts["SF-04"].expected_relation is (
        StylizedFactExpectation.POSITIVE_AGGRESSOR_FLOW_PRICE_IMPACT
    )
    assert dict(facts["SF-04"].parameters)["flow_series"] == ("aggressor-executed-flow-imbalance")

    assert facts["SF-05"].expected_relation is (
        StylizedFactExpectation.STRONGER_IMPACT_AT_LOW_DEPTH
    )
    assert dict(facts["SF-05"].parameters)["low_depth_quantile"] == "0.25"
    assert dict(facts["SF-05"].parameters)["high_depth_quantile"] == "0.75"

    assert facts["SF-06"].expected_relation is (StylizedFactExpectation.LIQUIDITY_FRAGILITY)


def test_protocol_matches_bundled_snapshot_and_fingerprint() -> None:
    protocol = stylized_fact_validation_protocol()

    verify_bundled_stylized_validation_protocol(protocol)
    assert protocol.to_mapping() == bundled_stylized_validation_protocol_mapping()
    assert (
        protocol.fingerprint == "a0906ab5529e78c8410448eb2e1bede78a3ab2f295d2500d5dc277a5dccf0b6b"
    )


def test_long_horizon_config_preserves_flagship_control_ecology() -> None:
    protocol = stylized_fact_validation_protocol()
    flagship = flagship_narrative_stability_protocol()
    config = build_stylized_validation_benchmark_config(protocol)

    assert protocol.source_flagship_protocol_fingerprint == flagship.fingerprint
    assert config.periods == 4352
    assert config.scenario_id == protocol.protocol_id
    assert config.direction_schedule[:4] == protocol.direction_cycle
    assert config.direction_schedule[-4:] == protocol.direction_cycle
    assert config.direction_schedule == protocol.direction_cycle * 1088

    assert config.fundamental_value == flagship.benchmark_config.fundamental_value
    assert config.tick_size == flagship.benchmark_config.tick_size
    assert config.lot_size == flagship.benchmark_config.lot_size
    assert config.passive_levels == flagship.benchmark_config.passive_levels
    assert config.passive_quantity_per_level == flagship.benchmark_config.passive_quantity_per_level
    assert config.narrative_agent_count == (flagship.benchmark_config.narrative_agent_count)
    assert config.noise_trader_count == flagship.benchmark_config.noise_trader_count
    assert config.noise_activity_bps == flagship.benchmark_config.noise_activity_bps
    assert protocol.direction_cycle == (
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
    )


def test_stylized_validation_seed_tuple_is_frozen_and_unique() -> None:
    protocol = stylized_fact_validation_protocol()
    seeds = stylized_validation_seed_tuple(protocol)

    assert seeds == (
        14293940350402680862,
        10844280713343619051,
        422821973909564885,
        7739049011184111908,
        5099198514136144343,
        5768764986067972836,
        314766522240548518,
        6764659870465496205,
        571526533512251032,
        17144515053621082801,
        8683684704711303559,
        17723955104321917404,
        7578505318181067512,
        3809187482411194634,
        3719334142630305312,
        9008933962056639588,
    )
    assert len(seeds) == 16
    assert len(set(seeds)) == 16
