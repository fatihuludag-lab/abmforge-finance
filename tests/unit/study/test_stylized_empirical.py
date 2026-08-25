"""Tests for the source-neutral Phase 11 empirical adapter."""

from __future__ import annotations

import math

import pytest

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.stylized_empirical import (
    EMPIRICAL_MARKET_SIGNATURE_PREPARATION_ID,
    EmpiricalMarketInterval,
    prepare_empirical_market_signature_sample,
)
from abmforge_finance.study.stylized_pipeline import (
    MarketSignatureSourceKind,
    estimate_prepared_market_signatures,
)

_INTERVAL_NS = 1_000_000_000


def _interval(index: int) -> EmpiricalMarketInterval:
    start = index * _INTERVAL_NS

    return EmpiricalMarketInterval(
        start_timestamp_ns=start,
        end_timestamp_ns=start + _INTERVAL_NS,
        mid_price=10_000.0 + index + (index % 3) * 0.2,
        aggressor_flow=(1.0 if index % 2 == 0 else -1.0),
        thin_side_depth=10.0 + (index % 7),
    )


def _intervals(
    count: int = 24,
) -> tuple[EmpiricalMarketInterval, ...]:
    return tuple(_interval(index) for index in range(count))


def test_empirical_interval_normalizes_numeric_values() -> None:
    interval = EmpiricalMarketInterval(
        start_timestamp_ns=0,
        end_timestamp_ns=1,
        mid_price=100,
        aggressor_flow=-2,
        thin_side_depth=5,
    )

    assert interval.mid_price == 100.0
    assert interval.aggressor_flow == -2.0
    assert interval.thin_side_depth == 5.0


def test_empirical_adapter_aligns_consecutive_intervals() -> None:
    intervals = _intervals()

    sample = prepare_empirical_market_signature_sample(
        intervals,
        source_id="empirical-smoke",
    )

    assert sample.data.observation_count == 23
    assert sample.provenance.source_kind is MarketSignatureSourceKind.EMPIRICAL
    assert sample.provenance.source_id == "empirical-smoke"
    assert sample.provenance.preparation_id == (EMPIRICAL_MARKET_SIGNATURE_PREPARATION_ID)

    expected_return = math.log(intervals[1].mid_price / intervals[0].mid_price)

    expected_drop = (intervals[0].thin_side_depth - intervals[1].thin_side_depth) / intervals[
        0
    ].thin_side_depth

    assert sample.data.log_returns[0] == pytest.approx(expected_return)
    assert sample.data.aggressor_flow[0] == (intervals[1].aggressor_flow)
    assert sample.data.pre_interval_thin_side_depth[0] == intervals[0].thin_side_depth
    assert sample.data.relative_thin_side_depth_drop[0] == pytest.approx(expected_drop)


def test_empirical_adapter_runs_through_shared_pipeline() -> None:
    sample = prepare_empirical_market_signature_sample(
        _intervals(),
        source_id="empirical-e2e",
    )

    estimates = estimate_prepared_market_signatures(sample)

    assert estimates.sf01_return_linear_dependence.observation_count == 23
    assert estimates.sf04_aggressor_flow_price_impact.observation_count == 23
    assert estimates.sf07_aggressor_sign_persistence.nonzero_observation_count == 23

    assert math.isfinite(estimates.sf04_aggressor_flow_price_impact.slope)
    assert math.isfinite(estimates.sf06_liquidity_fragility.depletion_spearman)


def test_empirical_adapter_rejects_too_few_intervals() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="at least 22 intervals",
    ):
        prepare_empirical_market_signature_sample(
            _intervals(21),
            source_id="too-short",
        )


def test_empirical_adapter_rejects_gap() -> None:
    intervals = list(_intervals())

    intervals[10] = EmpiricalMarketInterval(
        start_timestamp_ns=(intervals[9].end_timestamp_ns + 1),
        end_timestamp_ns=(intervals[9].end_timestamp_ns + 1 + _INTERVAL_NS),
        mid_price=intervals[10].mid_price,
        aggressor_flow=intervals[10].aggressor_flow,
        thin_side_depth=intervals[10].thin_side_depth,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="contiguous",
    ):
        prepare_empirical_market_signature_sample(
            tuple(intervals),
            source_id="gap",
        )


def test_empirical_adapter_rejects_unequal_interval_width() -> None:
    intervals = list(_intervals())

    target = intervals[-1]

    intervals[-1] = EmpiricalMarketInterval(
        start_timestamp_ns=target.start_timestamp_ns,
        end_timestamp_ns=target.end_timestamp_ns + 1,
        mid_price=target.mid_price,
        aggressor_flow=target.aggressor_flow,
        thin_side_depth=target.thin_side_depth,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="equal width",
    ):
        prepare_empirical_market_signature_sample(
            tuple(intervals),
            source_id="unequal-width",
        )


def test_empirical_interval_rejects_non_positive_midpoint() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="mid_price must be positive",
    ):
        EmpiricalMarketInterval(
            start_timestamp_ns=0,
            end_timestamp_ns=1,
            mid_price=0.0,
            aggressor_flow=1.0,
            thin_side_depth=1.0,
        )


def test_empirical_interval_rejects_negative_depth() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="thin_side_depth must be non-negative",
    ):
        EmpiricalMarketInterval(
            start_timestamp_ns=0,
            end_timestamp_ns=1,
            mid_price=100.0,
            aggressor_flow=1.0,
            thin_side_depth=-1.0,
        )


def test_empirical_adapter_rejects_zero_pre_interval_depth() -> None:
    intervals = list(_intervals())

    first = intervals[0]

    intervals[0] = EmpiricalMarketInterval(
        start_timestamp_ns=first.start_timestamp_ns,
        end_timestamp_ns=first.end_timestamp_ns,
        mid_price=first.mid_price,
        aggressor_flow=first.aggressor_flow,
        thin_side_depth=0.0,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="pre-interval thin-side depth must be positive",
    ):
        prepare_empirical_market_signature_sample(
            tuple(intervals),
            source_id="zero-pre-depth",
        )


def test_empirical_adapter_requires_tuple() -> None:
    with pytest.raises(
        TypeError,
        match="intervals must be a tuple",
    ):
        prepare_empirical_market_signature_sample(
            list(_intervals()),  # type: ignore[arg-type]
            source_id="invalid-container",
        )


def test_empirical_zero_flow_is_preserved_not_imputed_or_dropped() -> None:
    intervals = list(_intervals())

    target = intervals[5]

    intervals[5] = EmpiricalMarketInterval(
        start_timestamp_ns=target.start_timestamp_ns,
        end_timestamp_ns=target.end_timestamp_ns,
        mid_price=target.mid_price,
        aggressor_flow=0.0,
        thin_side_depth=target.thin_side_depth,
    )

    sample = prepare_empirical_market_signature_sample(
        tuple(intervals),
        source_id="zero-flow",
    )

    assert sample.data.aggressor_flow[4] == 0.0
    assert sample.data.observation_count == 23


def test_empirical_interval_rejects_non_numeric_value() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="finite real number",
    ):
        EmpiricalMarketInterval(
            start_timestamp_ns=0,
            end_timestamp_ns=1,
            mid_price="100",  # type: ignore[arg-type]
            aggressor_flow=1.0,
            thin_side_depth=1.0,
        )


def test_empirical_interval_rejects_non_finite_value() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="finite real number",
    ):
        EmpiricalMarketInterval(
            start_timestamp_ns=0,
            end_timestamp_ns=1,
            mid_price=float("inf"),
            aggressor_flow=1.0,
            thin_side_depth=1.0,
        )


def test_empirical_interval_rejects_boolean_timestamp() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="non-negative integer",
    ):
        EmpiricalMarketInterval(
            start_timestamp_ns=True,
            end_timestamp_ns=1,
            mid_price=100.0,
            aggressor_flow=1.0,
            thin_side_depth=1.0,
        )


def test_empirical_interval_rejects_negative_timestamp() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="non-negative integer",
    ):
        EmpiricalMarketInterval(
            start_timestamp_ns=-1,
            end_timestamp_ns=1,
            mid_price=100.0,
            aggressor_flow=1.0,
            thin_side_depth=1.0,
        )


def test_empirical_interval_rejects_non_increasing_timestamp() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="greater than start_timestamp_ns",
    ):
        EmpiricalMarketInterval(
            start_timestamp_ns=10,
            end_timestamp_ns=10,
            mid_price=100.0,
            aggressor_flow=1.0,
            thin_side_depth=1.0,
        )


def test_empirical_adapter_rejects_invalid_interval_member() -> None:
    intervals = _intervals()

    invalid = (
        *intervals[:5],
        object(),
        *intervals[6:],
    )

    with pytest.raises(
        TypeError,
        match=r"intervals\[5\].*EmpiricalMarketInterval",
    ):
        prepare_empirical_market_signature_sample(
            invalid,  # type: ignore[arg-type]
            source_id="invalid-member",
        )
