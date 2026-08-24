"""Oracle tests for shared Phase 11 market-signature estimators."""

from __future__ import annotations

import pytest

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.stylized_estimators import (
    estimate_absolute_log_return_acf,
    estimate_aggressor_flow_price_impact_ols,
    estimate_aggressor_sign_acf,
    estimate_depth_conditioned_aggressor_flow_impact_ols,
    estimate_liquidity_fragility_spearman,
    estimate_log_return_acf,
    estimate_market_signatures,
    estimate_return_tail_shape,
)


def test_sf01_log_return_acf_matches_hand_calculated_oracle() -> None:
    estimate = estimate_log_return_acf(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        maximum_lag=2,
    )

    assert estimate.lag_acf == pytest.approx((0.4, -0.1))
    assert estimate.mean_absolute_acf == pytest.approx(0.25)
    assert estimate.observation_count == 5


def test_sf02_return_tail_shape_matches_moment_oracle() -> None:
    estimate = estimate_return_tail_shape([-2.0, -1.0, 0.0, 1.0, 2.0])

    assert estimate.excess_kurtosis == pytest.approx(-1.3)
    assert estimate.two_sided_tail_probability == pytest.approx(0.0)
    assert estimate.observation_count == 5


def test_sf02_tail_probability_uses_strict_sigma_threshold() -> None:
    estimate = estimate_return_tail_shape(
        [-2.0, -1.0, 0.0, 1.0, 2.0],
        tail_threshold_sigma=1.0,
    )

    assert estimate.two_sided_tail_probability == pytest.approx(0.4)


def test_sf03_absolute_return_acf_matches_hand_calculated_oracle() -> None:
    estimate = estimate_absolute_log_return_acf(
        [1.0, -2.0, 3.0, -4.0, 5.0],
        maximum_lag=2,
    )

    assert estimate.lag_acf == pytest.approx((0.4, -0.1))
    assert estimate.mean_acf == pytest.approx(0.15)
    assert estimate.observation_count == 5


def test_sf04_aggressor_flow_ols_recovers_intercept_and_slope() -> None:
    estimate = estimate_aggressor_flow_price_impact_ols(
        log_returns=[0.0, 0.5, 1.0, 1.5, 2.0],
        aggressor_flow=[-2.0, -1.0, 0.0, 1.0, 2.0],
    )

    assert estimate.intercept == pytest.approx(1.0)
    assert estimate.slope == pytest.approx(0.5)
    assert estimate.observation_count == 5


def test_sf05_depth_conditioned_impact_recovers_known_slopes() -> None:
    estimate = estimate_depth_conditioned_aggressor_flow_impact_ols(
        log_returns=[
            1.0,
            3.0,
            0.0,
            0.0,
            0.0,
            0.0,
            4.0,
            5.0,
        ],
        aggressor_flow=[
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            2.0,
        ],
        pre_interval_thin_side_depth=[
            1.0,
            2.0,
            3.0,
            4.0,
            5.0,
            6.0,
            7.0,
            8.0,
        ],
    )

    assert estimate.low_depth_threshold == pytest.approx(2.75)
    assert estimate.high_depth_threshold == pytest.approx(6.25)

    assert estimate.low_depth.intercept == pytest.approx(1.0)
    assert estimate.low_depth.slope == pytest.approx(2.0)
    assert estimate.low_depth.observation_count == 2

    assert estimate.high_depth.intercept == pytest.approx(4.0)
    assert estimate.high_depth.slope == pytest.approx(0.5)
    assert estimate.high_depth.observation_count == 2

    assert estimate.low_minus_high_absolute_slope == pytest.approx(1.5)


def test_sf06_liquidity_fragility_matches_rank_correlation_oracle() -> None:
    estimate = estimate_liquidity_fragility_spearman(
        log_returns=[1.0, -2.0, 3.0, -4.0],
        relative_thin_side_depth_drop=[0.1, 0.2, 0.3, 0.4],
        pre_interval_thin_side_depth=[4.0, 3.0, 2.0, 1.0],
    )

    assert estimate.depletion_spearman == pytest.approx(1.0)
    assert estimate.pre_depth_spearman == pytest.approx(-1.0)
    assert estimate.observation_count == 4


def test_sf06_spearman_handles_tied_ranks_with_average_ranks() -> None:
    estimate = estimate_liquidity_fragility_spearman(
        log_returns=[1.0, -1.0, 2.0, -2.0, 3.0],
        relative_thin_side_depth_drop=[1.0, 1.0, 2.0, 2.0, 3.0],
        pre_interval_thin_side_depth=[3.0, 3.0, 2.0, 2.0, 1.0],
    )

    assert estimate.depletion_spearman == pytest.approx(1.0)
    assert estimate.pre_depth_spearman == pytest.approx(-1.0)


def test_sf07_aggressor_sign_acf_omits_zero_flow_intervals() -> None:
    estimate = estimate_aggressor_sign_acf(
        [1.0, 0.0, -2.0, 0.0, 3.0, -4.0],
        maximum_lag=2,
    )

    assert estimate.lag_acf == pytest.approx((-0.75, 0.5))
    assert estimate.mean_acf == pytest.approx(-0.125)
    assert estimate.nonzero_observation_count == 4


def test_constant_series_is_rejected_when_acf_is_undefined() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="positive variance",
    ):
        estimate_log_return_acf(
            [1.0, 1.0, 1.0, 1.0],
            maximum_lag=1,
        )


def test_ols_rejects_constant_predictor() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="positive variance",
    ):
        estimate_aggressor_flow_price_impact_ols(
            log_returns=[1.0, 2.0, 3.0],
            aggressor_flow=[2.0, 2.0, 2.0],
        )


def test_non_finite_observation_is_rejected() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="finite real number",
    ):
        estimate_return_tail_shape([0.0, 1.0, float("nan")])


def test_sf07_requires_two_nonzero_flow_observations() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="at least two non-zero observations",
    ):
        estimate_aggressor_sign_acf(
            [0.0, 1.0, 0.0],
            maximum_lag=1,
        )


def test_market_signature_bundle_rejects_unaligned_inputs() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="same length",
    ):
        estimate_market_signatures(
            log_returns=[1.0, 2.0, 3.0],
            aggressor_flow=[1.0, 2.0],
            pre_interval_thin_side_depth=[3.0, 2.0, 1.0],
            relative_thin_side_depth_drop=[0.1, 0.2, 0.3],
            maximum_lag=1,
        )


def test_sf01_acf_is_invariant_to_translation_and_positive_scaling() -> None:
    baseline = estimate_log_return_acf(
        [1.0, 2.0, 4.0, 3.0, 6.0, 5.0],
        maximum_lag=3,
    )

    transformed = estimate_log_return_acf(
        [13.0, 16.0, 22.0, 19.0, 28.0, 25.0],
        maximum_lag=3,
    )

    assert transformed.lag_acf == pytest.approx(baseline.lag_acf)
    assert transformed.mean_absolute_acf == pytest.approx(baseline.mean_absolute_acf)


def test_sf07_zero_insertion_does_not_change_sign_acf() -> None:
    baseline = estimate_aggressor_sign_acf(
        [2.0, -1.0, 3.0, -4.0, 5.0],
        maximum_lag=2,
    )

    with_zero_intervals = estimate_aggressor_sign_acf(
        [0.0, 2.0, 0.0, -1.0, 3.0, 0.0, -4.0, 0.0, 5.0],
        maximum_lag=2,
    )

    assert with_zero_intervals.lag_acf == pytest.approx(baseline.lag_acf)
    assert with_zero_intervals.mean_acf == pytest.approx(baseline.mean_acf)
    assert with_zero_intervals.nonzero_observation_count == baseline.nonzero_observation_count


def test_sf06_spearman_is_invariant_to_monotone_rescaling() -> None:
    baseline = estimate_liquidity_fragility_spearman(
        log_returns=[1.0, -2.0, 3.0, -4.0, 5.0],
        relative_thin_side_depth_drop=[1.0, 3.0, 2.0, 5.0, 4.0],
        pre_interval_thin_side_depth=[5.0, 4.0, 3.0, 2.0, 1.0],
    )

    transformed = estimate_liquidity_fragility_spearman(
        log_returns=[1.0, -4.0, 9.0, -16.0, 25.0],
        relative_thin_side_depth_drop=[1.0, 9.0, 4.0, 25.0, 16.0],
        pre_interval_thin_side_depth=[20.0, 18.0, 16.0, 14.0, 12.0],
    )

    assert transformed.depletion_spearman == pytest.approx(baseline.depletion_spearman)
    assert transformed.pre_depth_spearman == pytest.approx(baseline.pre_depth_spearman)


def test_market_signature_bundle_is_deterministic() -> None:
    log_returns = [
        1.0,
        3.0,
        -1.0,
        2.0,
        -2.0,
        4.0,
        4.0,
        5.0,
    ]
    aggressor_flow = [
        0.0,
        1.0,
        -1.0,
        1.0,
        -2.0,
        2.0,
        0.0,
        2.0,
    ]
    pre_interval_thin_side_depth = [
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
        6.0,
        7.0,
        8.0,
    ]
    relative_thin_side_depth_drop = [
        0.10,
        0.20,
        0.15,
        0.40,
        0.30,
        0.50,
        0.60,
        0.70,
    ]

    first = estimate_market_signatures(
        log_returns=log_returns,
        aggressor_flow=aggressor_flow,
        pre_interval_thin_side_depth=pre_interval_thin_side_depth,
        relative_thin_side_depth_drop=relative_thin_side_depth_drop,
        maximum_lag=2,
    )
    second = estimate_market_signatures(
        log_returns=log_returns,
        aggressor_flow=aggressor_flow,
        pre_interval_thin_side_depth=pre_interval_thin_side_depth,
        relative_thin_side_depth_drop=relative_thin_side_depth_drop,
        maximum_lag=2,
    )

    assert first == second


def test_market_signature_bundle_returns_all_seven_signatures() -> None:
    estimate = estimate_market_signatures(
        log_returns=[
            1.0,
            3.0,
            -1.0,
            2.0,
            -2.0,
            4.0,
            4.0,
            5.0,
        ],
        aggressor_flow=[
            0.0,
            1.0,
            -1.0,
            1.0,
            -2.0,
            2.0,
            0.0,
            2.0,
        ],
        pre_interval_thin_side_depth=[
            1.0,
            2.0,
            3.0,
            4.0,
            5.0,
            6.0,
            7.0,
            8.0,
        ],
        relative_thin_side_depth_drop=[
            0.10,
            0.20,
            0.15,
            0.40,
            0.30,
            0.50,
            0.60,
            0.70,
        ],
        maximum_lag=2,
    )

    assert estimate.sf01_return_linear_dependence.observation_count == 8
    assert estimate.sf02_return_tail_shape.observation_count == 8
    assert estimate.sf03_volatility_clustering.observation_count == 8
    assert estimate.sf04_aggressor_flow_price_impact.observation_count == 8
    assert estimate.sf05_depth_conditioned_price_impact.low_depth.observation_count == 2
    assert estimate.sf05_depth_conditioned_price_impact.high_depth.observation_count == 2
    assert estimate.sf06_liquidity_fragility.observation_count == 8
    assert estimate.sf07_aggressor_sign_persistence.nonzero_observation_count == 6


def test_acf_rejects_lag_equal_to_observation_count() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="smaller than the number of observations",
    ):
        estimate_log_return_acf(
            [1.0, 2.0, 3.0],
            maximum_lag=3,
        )


def test_acf_rejects_non_positive_maximum_lag() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="maximum_lag must be positive",
    ):
        estimate_log_return_acf(
            [1.0, 2.0, 3.0],
            maximum_lag=0,
        )


def test_sf05_rejects_reversed_depth_quantiles() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="low_depth_quantile must be smaller",
    ):
        estimate_depth_conditioned_aggressor_flow_impact_ols(
            log_returns=[1.0, 2.0, 3.0, 4.0],
            aggressor_flow=[0.0, 1.0, 0.0, 1.0],
            pre_interval_thin_side_depth=[1.0, 2.0, 3.0, 4.0],
            low_depth_quantile=0.75,
            high_depth_quantile=0.25,
        )


def test_sf05_rejects_negative_depth() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="must be non-negative",
    ):
        estimate_depth_conditioned_aggressor_flow_impact_ols(
            log_returns=[1.0, 2.0, 3.0, 4.0],
            aggressor_flow=[0.0, 1.0, 0.0, 1.0],
            pre_interval_thin_side_depth=[
                1.0,
                -2.0,
                3.0,
                4.0,
            ],
        )


def test_sf02_rejects_non_positive_tail_threshold() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="positive and finite",
    ):
        estimate_return_tail_shape(
            [-1.0, 0.0, 1.0],
            tail_threshold_sigma=0.0,
        )


def test_estimator_rejects_single_observation() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="at least 2 observations",
    ):
        estimate_return_tail_shape([1.0])


def test_estimator_rejects_boolean_observation() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="finite real number",
    ):
        estimate_return_tail_shape([0.0, 1.0, True])


def test_acf_rejects_boolean_maximum_lag() -> None:
    with pytest.raises(
        TypeError,
        match="maximum_lag must be an integer",
    ):
        estimate_log_return_acf(
            [1.0, 2.0, 3.0],
            maximum_lag=True,
        )


def test_tail_shape_rejects_boolean_threshold() -> None:
    with pytest.raises(
        TypeError,
        match="tail_threshold_sigma must be a real number",
    ):
        estimate_return_tail_shape(
            [-1.0, 0.0, 1.0],
            tail_threshold_sigma=True,
        )


def test_tail_shape_rejects_non_finite_threshold() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="positive and finite",
    ):
        estimate_return_tail_shape(
            [-1.0, 0.0, 1.0],
            tail_threshold_sigma=float("inf"),
        )


def test_sf04_rejects_unaligned_series() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="same number of observations",
    ):
        estimate_aggressor_flow_price_impact_ols(
            log_returns=[1.0, 2.0, 3.0],
            aggressor_flow=[1.0, 2.0],
        )


def test_sf05_rejects_boolean_quantile() -> None:
    with pytest.raises(
        TypeError,
        match="low_depth_quantile must be a real number",
    ):
        estimate_depth_conditioned_aggressor_flow_impact_ols(
            log_returns=[1.0, 2.0, 3.0, 4.0],
            aggressor_flow=[0.0, 1.0, 0.0, 1.0],
            pre_interval_thin_side_depth=[1.0, 2.0, 3.0, 4.0],
            low_depth_quantile=True,
        )


def test_sf05_rejects_boundary_quantile() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="strictly between 0 and 1",
    ):
        estimate_depth_conditioned_aggressor_flow_impact_ols(
            log_returns=[1.0, 2.0, 3.0, 4.0],
            aggressor_flow=[0.0, 1.0, 0.0, 1.0],
            pre_interval_thin_side_depth=[1.0, 2.0, 3.0, 4.0],
            low_depth_quantile=0.0,
        )


def test_sf05_type7_quantile_supports_exact_order_position() -> None:
    estimate = estimate_depth_conditioned_aggressor_flow_impact_ols(
        log_returns=[1.0, 3.0, 0.0, 4.0, 5.0],
        aggressor_flow=[0.0, 1.0, 0.0, 0.0, 2.0],
        pre_interval_thin_side_depth=[1.0, 2.0, 3.0, 4.0, 5.0],
    )

    assert estimate.low_depth_threshold == pytest.approx(2.0)
    assert estimate.high_depth_threshold == pytest.approx(4.0)


def test_sf05_rejects_non_distinct_depth_strata() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="distinct low- and high-depth strata",
    ):
        estimate_depth_conditioned_aggressor_flow_impact_ols(
            log_returns=[1.0, 2.0, 3.0, 4.0],
            aggressor_flow=[0.0, 1.0, 2.0, 3.0],
            pre_interval_thin_side_depth=[2.0, 2.0, 2.0, 2.0],
        )


def test_sf05_rejects_depth_strata_with_too_few_observations() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="each depth stratum must contain at least two",
    ):
        estimate_depth_conditioned_aggressor_flow_impact_ols(
            log_returns=[1.0, 2.0],
            aggressor_flow=[0.0, 1.0],
            pre_interval_thin_side_depth=[1.0, 2.0],
        )


def test_sf05_rejects_unaligned_flow() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="same number of observations",
    ):
        estimate_depth_conditioned_aggressor_flow_impact_ols(
            log_returns=[1.0, 2.0, 3.0, 4.0],
            aggressor_flow=[0.0, 1.0, 2.0],
            pre_interval_thin_side_depth=[1.0, 2.0, 3.0, 4.0],
        )


def test_sf06_rejects_unaligned_depletion_series() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="same number of observations",
    ):
        estimate_liquidity_fragility_spearman(
            log_returns=[1.0, -2.0, 3.0, -4.0],
            relative_thin_side_depth_drop=[0.1, 0.2, 0.3],
            pre_interval_thin_side_depth=[4.0, 3.0, 2.0, 1.0],
        )


def test_sf06_rejects_negative_pre_interval_depth() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="must be non-negative",
    ):
        estimate_liquidity_fragility_spearman(
            log_returns=[1.0, -2.0, 3.0, -4.0],
            relative_thin_side_depth_drop=[0.1, 0.2, 0.3, 0.4],
            pre_interval_thin_side_depth=[4.0, 3.0, -2.0, 1.0],
        )


def test_sf06_rejects_constant_absolute_return_ranks() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="positive variance",
    ):
        estimate_liquidity_fragility_spearman(
            log_returns=[1.0, -1.0, 1.0, -1.0],
            relative_thin_side_depth_drop=[0.1, 0.2, 0.3, 0.4],
            pre_interval_thin_side_depth=[4.0, 3.0, 2.0, 1.0],
        )


def test_sf06_rejects_constant_depletion_ranks() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="positive variance",
    ):
        estimate_liquidity_fragility_spearman(
            log_returns=[1.0, -2.0, 3.0, -4.0],
            relative_thin_side_depth_drop=[0.2, 0.2, 0.2, 0.2],
            pre_interval_thin_side_depth=[4.0, 3.0, 2.0, 1.0],
        )


def test_sf07_rejects_constant_nonzero_sign_series() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="positive variance",
    ):
        estimate_aggressor_sign_acf(
            [1.0, 2.0, 3.0, 4.0],
            maximum_lag=1,
        )
