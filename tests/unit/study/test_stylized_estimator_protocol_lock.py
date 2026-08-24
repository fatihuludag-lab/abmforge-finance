"""Protocol-lock tests for shared Phase 11 stylized-fact estimators."""

from __future__ import annotations

from inspect import signature

from abmforge_finance.study import (
    StylizedFactSpec,
    estimate_absolute_log_return_acf,
    estimate_aggressor_flow_price_impact_ols,
    estimate_aggressor_sign_acf,
    estimate_depth_conditioned_aggressor_flow_impact_ols,
    estimate_liquidity_fragility_spearman,
    estimate_log_return_acf,
    estimate_market_signatures,
    estimate_return_tail_shape,
    stylized_fact_validation_protocol,
)


def _fact(fact_id: str) -> StylizedFactSpec:
    protocol = stylized_fact_validation_protocol()

    for fact in protocol.facts:
        if fact.fact_id == fact_id:
            return fact

    raise AssertionError(f"missing frozen stylized fact: {fact_id}")


def test_every_frozen_estimator_id_has_one_shared_implementation() -> None:
    implementations = {
        "log-return-acf": estimate_log_return_acf,
        "return-tail-shape": estimate_return_tail_shape,
        "absolute-log-return-acf": estimate_absolute_log_return_acf,
        "aggressor-flow-price-impact-ols": (estimate_aggressor_flow_price_impact_ols),
        "depth-conditioned-aggressor-flow-impact-ols": (
            estimate_depth_conditioned_aggressor_flow_impact_ols
        ),
        "liquidity-fragility-spearman": (estimate_liquidity_fragility_spearman),
        "aggressor-sign-acf": estimate_aggressor_sign_acf,
    }

    protocol = stylized_fact_validation_protocol()

    frozen_ids = {fact.estimator_id for fact in protocol.facts}

    assert set(implementations) == frozen_ids


def test_bundle_maximum_lag_default_matches_frozen_protocol() -> None:
    protocol = stylized_fact_validation_protocol()
    parameters = signature(estimate_market_signatures).parameters

    assert parameters["maximum_lag"].default == protocol.maximum_acf_lag


def test_bundle_tail_threshold_default_matches_sf02() -> None:
    parameters = signature(estimate_market_signatures).parameters
    sf02_parameters = dict(_fact("SF-02").parameters)

    assert parameters["tail_threshold_sigma"].default == float(
        sf02_parameters["tail_threshold_sigma"]
    )


def test_bundle_depth_quantile_defaults_match_sf05() -> None:
    parameters = signature(estimate_market_signatures).parameters
    sf05_parameters = dict(_fact("SF-05").parameters)

    assert parameters["low_depth_quantile"].default == float(sf05_parameters["low_depth_quantile"])
    assert parameters["high_depth_quantile"].default == float(
        sf05_parameters["high_depth_quantile"]
    )


def test_protocol_requires_same_estimator_implementation() -> None:
    protocol = stylized_fact_validation_protocol()

    assert protocol.estimator_lock == (
        "same-estimator-implementation-for-simulation-and-empirical-data"
    )
