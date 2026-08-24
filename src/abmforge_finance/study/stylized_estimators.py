"""Shared source-agnostic estimators for Phase 11 stylized market signatures."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from abmforge_finance.exceptions import InvalidMetricInputError


@dataclass(frozen=True, slots=True)
class ReturnAutocorrelationEstimate:
    """SF-01 return-linear-dependence estimate."""

    lag_acf: tuple[float, ...]
    mean_absolute_acf: float
    observation_count: int


@dataclass(frozen=True, slots=True)
class ReturnTailShapeEstimate:
    """SF-02 return-tail-shape estimate."""

    excess_kurtosis: float
    two_sided_tail_probability: float
    observation_count: int


@dataclass(frozen=True, slots=True)
class AbsoluteReturnAutocorrelationEstimate:
    """SF-03 volatility-clustering estimate."""

    lag_acf: tuple[float, ...]
    mean_acf: float
    observation_count: int


@dataclass(frozen=True, slots=True)
class OlsEstimate:
    """Intercept-inclusive ordinary-least-squares estimate."""

    intercept: float
    slope: float
    observation_count: int


@dataclass(frozen=True, slots=True)
class DepthConditionedImpactEstimate:
    """SF-05 low- versus high-depth price-impact estimate."""

    low_depth_threshold: float
    high_depth_threshold: float
    low_depth: OlsEstimate
    high_depth: OlsEstimate
    low_minus_high_absolute_slope: float


@dataclass(frozen=True, slots=True)
class LiquidityFragilityEstimate:
    """SF-06 liquidity-fragility rank-correlation estimate."""

    depletion_spearman: float
    pre_depth_spearman: float
    observation_count: int


@dataclass(frozen=True, slots=True)
class AggressorSignAutocorrelationEstimate:
    """SF-07 aggressor-sign-persistence estimate."""

    lag_acf: tuple[float, ...]
    mean_acf: float
    nonzero_observation_count: int


@dataclass(frozen=True, slots=True)
class MarketSignatureEstimates:
    """Complete seven-signature Phase 11 estimator result."""

    sf01_return_linear_dependence: ReturnAutocorrelationEstimate
    sf02_return_tail_shape: ReturnTailShapeEstimate
    sf03_volatility_clustering: AbsoluteReturnAutocorrelationEstimate
    sf04_aggressor_flow_price_impact: OlsEstimate
    sf05_depth_conditioned_price_impact: DepthConditionedImpactEstimate
    sf06_liquidity_fragility: LiquidityFragilityEstimate
    sf07_aggressor_sign_persistence: AggressorSignAutocorrelationEstimate


def _finite_series(
    values: Sequence[float],
    *,
    label: str,
    minimum_size: int = 2,
) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be a numeric sequence")

    if len(values) < minimum_size:
        raise InvalidMetricInputError(f"{label} must contain at least {minimum_size} observations")

    output: list[float] = []

    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidMetricInputError(f"{label}[{index}] must be a finite real number")

        number = float(value)

        if not math.isfinite(number):
            raise InvalidMetricInputError(f"{label}[{index}] must be a finite real number")

        output.append(number)

    return tuple(output)


def _same_length(
    left: tuple[float, ...],
    right: tuple[float, ...],
    *,
    left_label: str,
    right_label: str,
) -> None:
    if len(left) != len(right):
        raise InvalidMetricInputError(
            f"{left_label} and {right_label} must contain the same number of observations"
        )


def _maximum_lag(value: int, *, observation_count: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("maximum_lag must be an integer")

    if value < 1:
        raise InvalidMetricInputError("maximum_lag must be positive")

    if value >= observation_count:
        raise InvalidMetricInputError("maximum_lag must be smaller than the number of observations")

    return value


def _positive_float(value: float, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a real number")

    number = float(value)

    if not math.isfinite(number) or number <= 0.0:
        raise InvalidMetricInputError(f"{label} must be positive and finite")

    return number


def _quantile_probability(value: float, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a real number")

    number = float(value)

    if not math.isfinite(number) or number <= 0.0 or number >= 1.0:
        raise InvalidMetricInputError(f"{label} must be finite and strictly between 0 and 1")

    return number


def _mean(values: tuple[float, ...]) -> float:
    return math.fsum(values) / len(values)


def _acf_from_finite_series(
    values: tuple[float, ...],
    *,
    maximum_lag: int,
    label: str,
) -> tuple[float, ...]:
    lag_limit = _maximum_lag(
        maximum_lag,
        observation_count=len(values),
    )

    mean = _mean(values)
    centered = tuple(value - mean for value in values)

    denominator = math.fsum(value * value for value in centered)

    if denominator == 0.0:
        raise InvalidMetricInputError(f"{label} must have positive variance")

    output: list[float] = []

    for lag in range(1, lag_limit + 1):
        numerator = math.fsum(
            centered[index] * centered[index - lag] for index in range(lag, len(centered))
        )

        value = numerator / denominator

        if not math.isfinite(value):
            raise InvalidMetricInputError(f"{label} autocorrelation is not finite")

        output.append(value)

    return tuple(output)


def _ols_from_finite_series(
    response: tuple[float, ...],
    predictor: tuple[float, ...],
    *,
    response_label: str,
    predictor_label: str,
) -> OlsEstimate:
    _same_length(
        response,
        predictor,
        left_label=response_label,
        right_label=predictor_label,
    )

    if len(response) < 2:
        raise InvalidMetricInputError("OLS requires at least two aligned observations")

    response_mean = _mean(response)
    predictor_mean = _mean(predictor)

    predictor_centered = tuple(value - predictor_mean for value in predictor)

    denominator = math.fsum(value * value for value in predictor_centered)

    if denominator == 0.0:
        raise InvalidMetricInputError(f"{predictor_label} must have positive variance")

    numerator = math.fsum(
        predictor_delta * (response_value - response_mean)
        for predictor_delta, response_value in zip(
            predictor_centered,
            response,
            strict=True,
        )
    )

    slope = numerator / denominator
    intercept = response_mean - slope * predictor_mean

    if not math.isfinite(slope) or not math.isfinite(intercept):
        raise InvalidMetricInputError("OLS estimate must be finite")

    return OlsEstimate(
        intercept=intercept,
        slope=slope,
        observation_count=len(response),
    )


def _type7_quantile(
    values: tuple[float, ...],
    probability: float,
) -> float:
    ordered = tuple(sorted(values))

    position = (len(ordered) - 1) * probability

    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return ordered[lower_index]

    weight = position - lower_index

    return ordered[lower_index] + weight * (ordered[upper_index] - ordered[lower_index])


def _average_ranks(
    values: tuple[float, ...],
) -> tuple[float, ...]:
    order = sorted(
        range(len(values)),
        key=values.__getitem__,
    )

    ranks = [0.0] * len(values)
    start = 0

    while start < len(order):
        end = start + 1

        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1

        average_rank = ((start + 1) + end) / 2.0

        for position in range(start, end):
            ranks[order[position]] = average_rank

        start = end

    return tuple(ranks)


def _pearson_from_finite_series(
    left: tuple[float, ...],
    right: tuple[float, ...],
    *,
    left_label: str,
    right_label: str,
) -> float:
    _same_length(
        left,
        right,
        left_label=left_label,
        right_label=right_label,
    )

    if len(left) < 2:
        raise InvalidMetricInputError("correlation requires at least two aligned observations")

    left_mean = _mean(left)
    right_mean = _mean(right)

    left_centered = tuple(value - left_mean for value in left)
    right_centered = tuple(value - right_mean for value in right)

    left_sum_squares = math.fsum(value * value for value in left_centered)
    right_sum_squares = math.fsum(value * value for value in right_centered)

    if left_sum_squares == 0.0:
        raise InvalidMetricInputError(f"{left_label} must have positive variance")

    if right_sum_squares == 0.0:
        raise InvalidMetricInputError(f"{right_label} must have positive variance")

    numerator = math.fsum(
        left_value * right_value
        for left_value, right_value in zip(
            left_centered,
            right_centered,
            strict=True,
        )
    )

    denominator = math.sqrt(left_sum_squares * right_sum_squares)

    correlation = numerator / denominator

    if not math.isfinite(correlation):
        raise InvalidMetricInputError("correlation estimate must be finite")

    return max(-1.0, min(1.0, correlation))


def _spearman_from_finite_series(
    left: tuple[float, ...],
    right: tuple[float, ...],
    *,
    left_label: str,
    right_label: str,
) -> float:
    return _pearson_from_finite_series(
        _average_ranks(left),
        _average_ranks(right),
        left_label=f"{left_label} ranks",
        right_label=f"{right_label} ranks",
    )


def estimate_log_return_acf(
    log_returns: Sequence[float],
    *,
    maximum_lag: int,
) -> ReturnAutocorrelationEstimate:
    """Estimate SF-01 using global-mean sample autocorrelation."""

    returns = _finite_series(
        log_returns,
        label="log_returns",
    )

    acf = _acf_from_finite_series(
        returns,
        maximum_lag=maximum_lag,
        label="log_returns",
    )

    return ReturnAutocorrelationEstimate(
        lag_acf=acf,
        mean_absolute_acf=(math.fsum(abs(value) for value in acf) / len(acf)),
        observation_count=len(returns),
    )


def estimate_return_tail_shape(
    log_returns: Sequence[float],
    *,
    tail_threshold_sigma: float = 3.0,
) -> ReturnTailShapeEstimate:
    """Estimate SF-02 moment kurtosis and empirical two-sided sigma tail."""

    returns = _finite_series(
        log_returns,
        label="log_returns",
    )

    threshold_sigma = _positive_float(
        tail_threshold_sigma,
        label="tail_threshold_sigma",
    )

    mean = _mean(returns)

    centered = tuple(value - mean for value in returns)

    second_moment = math.fsum(value * value for value in centered) / len(centered)

    if second_moment == 0.0:
        raise InvalidMetricInputError("log_returns must have positive variance")

    fourth_moment = math.fsum(value**4 for value in centered) / len(centered)

    excess_kurtosis = fourth_moment / (second_moment * second_moment) - 3.0

    standard_deviation = math.sqrt(second_moment)
    threshold = threshold_sigma * standard_deviation

    tail_probability = math.fsum(1.0 for value in centered if abs(value) > threshold) / len(
        centered
    )

    if not math.isfinite(excess_kurtosis):
        raise InvalidMetricInputError("excess kurtosis estimate must be finite")

    return ReturnTailShapeEstimate(
        excess_kurtosis=excess_kurtosis,
        two_sided_tail_probability=tail_probability,
        observation_count=len(returns),
    )


def estimate_absolute_log_return_acf(
    log_returns: Sequence[float],
    *,
    maximum_lag: int,
) -> AbsoluteReturnAutocorrelationEstimate:
    """Estimate SF-03 from autocorrelation of absolute log returns."""

    returns = _finite_series(
        log_returns,
        label="log_returns",
    )

    absolute_returns = tuple(abs(value) for value in returns)

    acf = _acf_from_finite_series(
        absolute_returns,
        maximum_lag=maximum_lag,
        label="absolute_log_returns",
    )

    return AbsoluteReturnAutocorrelationEstimate(
        lag_acf=acf,
        mean_acf=math.fsum(acf) / len(acf),
        observation_count=len(returns),
    )


def estimate_aggressor_flow_price_impact_ols(
    log_returns: Sequence[float],
    aggressor_flow: Sequence[float],
) -> OlsEstimate:
    """Estimate SF-04 with intercept-inclusive OLS."""

    returns = _finite_series(
        log_returns,
        label="log_returns",
    )

    flow = _finite_series(
        aggressor_flow,
        label="aggressor_flow",
    )

    return _ols_from_finite_series(
        returns,
        flow,
        response_label="log_returns",
        predictor_label="aggressor_flow",
    )


def estimate_depth_conditioned_aggressor_flow_impact_ols(
    log_returns: Sequence[float],
    aggressor_flow: Sequence[float],
    pre_interval_thin_side_depth: Sequence[float],
    *,
    low_depth_quantile: float = 0.25,
    high_depth_quantile: float = 0.75,
) -> DepthConditionedImpactEstimate:
    """Estimate SF-05 using Type-7 depth quantiles and separate OLS strata."""

    returns = _finite_series(
        log_returns,
        label="log_returns",
    )

    flow = _finite_series(
        aggressor_flow,
        label="aggressor_flow",
    )

    depth = _finite_series(
        pre_interval_thin_side_depth,
        label="pre_interval_thin_side_depth",
    )

    _same_length(
        returns,
        flow,
        left_label="log_returns",
        right_label="aggressor_flow",
    )

    _same_length(
        returns,
        depth,
        left_label="log_returns",
        right_label="pre_interval_thin_side_depth",
    )

    if any(value < 0.0 for value in depth):
        raise InvalidMetricInputError("pre_interval_thin_side_depth must be non-negative")

    low_probability = _quantile_probability(
        low_depth_quantile,
        label="low_depth_quantile",
    )

    high_probability = _quantile_probability(
        high_depth_quantile,
        label="high_depth_quantile",
    )

    if low_probability >= high_probability:
        raise InvalidMetricInputError("low_depth_quantile must be smaller than high_depth_quantile")

    low_threshold = _type7_quantile(
        depth,
        low_probability,
    )

    high_threshold = _type7_quantile(
        depth,
        high_probability,
    )

    if low_threshold >= high_threshold:
        raise InvalidMetricInputError(
            "depth quantiles must define distinct low- and high-depth strata"
        )

    low_indices = tuple(index for index, value in enumerate(depth) if value <= low_threshold)

    high_indices = tuple(index for index, value in enumerate(depth) if value >= high_threshold)

    if len(low_indices) < 2 or len(high_indices) < 2:
        raise InvalidMetricInputError("each depth stratum must contain at least two observations")

    low_estimate = _ols_from_finite_series(
        tuple(returns[index] for index in low_indices),
        tuple(flow[index] for index in low_indices),
        response_label="low_depth_log_returns",
        predictor_label="low_depth_aggressor_flow",
    )

    high_estimate = _ols_from_finite_series(
        tuple(returns[index] for index in high_indices),
        tuple(flow[index] for index in high_indices),
        response_label="high_depth_log_returns",
        predictor_label="high_depth_aggressor_flow",
    )

    return DepthConditionedImpactEstimate(
        low_depth_threshold=low_threshold,
        high_depth_threshold=high_threshold,
        low_depth=low_estimate,
        high_depth=high_estimate,
        low_minus_high_absolute_slope=(abs(low_estimate.slope) - abs(high_estimate.slope)),
    )


def estimate_liquidity_fragility_spearman(
    log_returns: Sequence[float],
    relative_thin_side_depth_drop: Sequence[float],
    pre_interval_thin_side_depth: Sequence[float],
) -> LiquidityFragilityEstimate:
    """Estimate SF-06 with Spearman rank correlations."""

    returns = _finite_series(
        log_returns,
        label="log_returns",
    )

    depletion = _finite_series(
        relative_thin_side_depth_drop,
        label="relative_thin_side_depth_drop",
    )

    depth = _finite_series(
        pre_interval_thin_side_depth,
        label="pre_interval_thin_side_depth",
    )

    _same_length(
        returns,
        depletion,
        left_label="log_returns",
        right_label="relative_thin_side_depth_drop",
    )

    _same_length(
        returns,
        depth,
        left_label="log_returns",
        right_label="pre_interval_thin_side_depth",
    )

    if any(value < 0.0 for value in depth):
        raise InvalidMetricInputError("pre_interval_thin_side_depth must be non-negative")

    absolute_returns = tuple(abs(value) for value in returns)

    return LiquidityFragilityEstimate(
        depletion_spearman=_spearman_from_finite_series(
            absolute_returns,
            depletion,
            left_label="absolute_log_returns",
            right_label="relative_thin_side_depth_drop",
        ),
        pre_depth_spearman=_spearman_from_finite_series(
            absolute_returns,
            depth,
            left_label="absolute_log_returns",
            right_label="pre_interval_thin_side_depth",
        ),
        observation_count=len(returns),
    )


def estimate_aggressor_sign_acf(
    aggressor_flow: Sequence[float],
    *,
    maximum_lag: int,
) -> AggressorSignAutocorrelationEstimate:
    """Estimate SF-07 after omitting zero-flow intervals."""

    flow = _finite_series(
        aggressor_flow,
        label="aggressor_flow",
    )

    signs = tuple(1.0 if value > 0.0 else -1.0 for value in flow if value != 0.0)

    if len(signs) < 2:
        raise InvalidMetricInputError(
            "aggressor_flow must contain at least two non-zero observations"
        )

    acf = _acf_from_finite_series(
        signs,
        maximum_lag=maximum_lag,
        label="aggressor_flow_sign",
    )

    return AggressorSignAutocorrelationEstimate(
        lag_acf=acf,
        mean_acf=math.fsum(acf) / len(acf),
        nonzero_observation_count=len(signs),
    )


def estimate_market_signatures(
    *,
    log_returns: Sequence[float],
    aggressor_flow: Sequence[float],
    pre_interval_thin_side_depth: Sequence[float],
    relative_thin_side_depth_drop: Sequence[float],
    maximum_lag: int = 20,
    tail_threshold_sigma: float = 3.0,
    low_depth_quantile: float = 0.25,
    high_depth_quantile: float = 0.75,
) -> MarketSignatureEstimates:
    """Estimate all seven Phase 11 signatures from aligned numeric series."""

    lengths = {
        len(log_returns),
        len(aggressor_flow),
        len(pre_interval_thin_side_depth),
        len(relative_thin_side_depth_drop),
    }

    if len(lengths) != 1:
        raise InvalidMetricInputError("all market-signature input series must have the same length")

    return MarketSignatureEstimates(
        sf01_return_linear_dependence=estimate_log_return_acf(
            log_returns,
            maximum_lag=maximum_lag,
        ),
        sf02_return_tail_shape=estimate_return_tail_shape(
            log_returns,
            tail_threshold_sigma=tail_threshold_sigma,
        ),
        sf03_volatility_clustering=(
            estimate_absolute_log_return_acf(
                log_returns,
                maximum_lag=maximum_lag,
            )
        ),
        sf04_aggressor_flow_price_impact=(
            estimate_aggressor_flow_price_impact_ols(
                log_returns,
                aggressor_flow,
            )
        ),
        sf05_depth_conditioned_price_impact=(
            estimate_depth_conditioned_aggressor_flow_impact_ols(
                log_returns,
                aggressor_flow,
                pre_interval_thin_side_depth,
                low_depth_quantile=low_depth_quantile,
                high_depth_quantile=high_depth_quantile,
            )
        ),
        sf06_liquidity_fragility=(
            estimate_liquidity_fragility_spearman(
                log_returns,
                relative_thin_side_depth_drop,
                pre_interval_thin_side_depth,
            )
        ),
        sf07_aggressor_sign_persistence=(
            estimate_aggressor_sign_acf(
                aggressor_flow,
                maximum_lag=maximum_lag,
            )
        ),
    )
