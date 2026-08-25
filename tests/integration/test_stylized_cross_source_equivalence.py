"""Cross-source equivalence tests for Phase 11 market-signature preparation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from abmforge_finance.recording import (
    FinanceResearchDataset,
    MarketStateRecord,
    OrderRecord,
)
from abmforge_finance.study.stylized_empirical import (
    EmpiricalMarketInterval,
    prepare_empirical_market_signature_sample,
)
from abmforge_finance.study.stylized_estimators import (
    MarketSignatureEstimates,
)
from abmforge_finance.study.stylized_pipeline import (
    estimate_prepared_market_signatures,
)
from abmforge_finance.study.stylized_protocol import (
    stylized_fact_validation_protocol,
)
from abmforge_finance.study.stylized_simulation import (
    prepare_stylized_validation_simulation_sample,
)

_INSTRUMENT = "CROSS-SOURCE"
_INTERVAL_NS = 1_000_000_000
_ZERO = Decimal("0")
_ONE = Decimal("1")


def _mid_price(period: int) -> Decimal:
    values = (
        Decimal("100"),
        Decimal("200"),
        Decimal("100"),
        Decimal("400"),
    )
    return values[period % len(values)]


def _market_state(period: int) -> MarketStateRecord:
    mid = _mid_price(period)

    return MarketStateRecord(
        period=period,
        instrument_id=_INSTRUMENT,
        fundamental_value=mid,
        best_bid=mid - _ONE,
        best_ask=mid + _ONE,
        mid_price=mid,
        spread=Decimal("2"),
        bid_depth=Decimal(10 + period % 7),
        ask_depth=Decimal(12 + period % 5),
        imbalance=None,
        order_count=1,
        last_trade_price=mid,
        price_change=None,
        fee_balance=_ZERO,
    )


def _aggressor_order(period: int) -> OrderRecord:
    return OrderRecord(
        period=period,
        order_id=f"cross-source-{period}",
        sequence_number=period,
        agent_id="agent",
        instrument_id=_INSTRUMENT,
        side="buy" if period % 2 == 0 else "sell",
        order_type="market",
        quantity=_ONE,
        limit_price=None,
        submitted_at=period,
        time_in_force="ioc",
        accepted=True,
        executed_quantity=_ONE,
        remaining_quantity=_ZERO,
        cancelled_quantity=_ZERO,
        rested=False,
        rejection_type=None,
        rejection_message=None,
    )


def _assert_estimates_equivalent(
    left: MarketSignatureEstimates,
    right: MarketSignatureEstimates,
) -> None:
    # Keep this helper local to the test so production estimators remain
    # source-agnostic and carry no comparison logic.
    left_result = left
    right_result = right

    assert left_result.sf01_return_linear_dependence.lag_acf == pytest.approx(
        right_result.sf01_return_linear_dependence.lag_acf
    )
    assert left_result.sf01_return_linear_dependence.mean_absolute_acf == pytest.approx(
        right_result.sf01_return_linear_dependence.mean_absolute_acf
    )

    assert left_result.sf02_return_tail_shape.excess_kurtosis == pytest.approx(
        right_result.sf02_return_tail_shape.excess_kurtosis
    )
    assert left_result.sf02_return_tail_shape.two_sided_tail_probability == pytest.approx(
        right_result.sf02_return_tail_shape.two_sided_tail_probability
    )

    assert left_result.sf03_volatility_clustering.lag_acf == pytest.approx(
        right_result.sf03_volatility_clustering.lag_acf
    )
    assert left_result.sf03_volatility_clustering.mean_acf == pytest.approx(
        right_result.sf03_volatility_clustering.mean_acf
    )

    assert left_result.sf04_aggressor_flow_price_impact.intercept == pytest.approx(
        right_result.sf04_aggressor_flow_price_impact.intercept
    )
    assert left_result.sf04_aggressor_flow_price_impact.slope == pytest.approx(
        right_result.sf04_aggressor_flow_price_impact.slope
    )

    left_sf05 = left_result.sf05_depth_conditioned_price_impact
    right_sf05 = right_result.sf05_depth_conditioned_price_impact

    assert left_sf05.low_depth_threshold == pytest.approx(right_sf05.low_depth_threshold)
    assert left_sf05.high_depth_threshold == pytest.approx(right_sf05.high_depth_threshold)
    assert left_sf05.low_depth.intercept == pytest.approx(right_sf05.low_depth.intercept)
    assert left_sf05.low_depth.slope == pytest.approx(right_sf05.low_depth.slope)
    assert left_sf05.high_depth.intercept == pytest.approx(right_sf05.high_depth.intercept)
    assert left_sf05.high_depth.slope == pytest.approx(right_sf05.high_depth.slope)
    assert left_sf05.low_minus_high_absolute_slope == pytest.approx(
        right_sf05.low_minus_high_absolute_slope
    )

    assert left_result.sf06_liquidity_fragility.depletion_spearman == pytest.approx(
        right_result.sf06_liquidity_fragility.depletion_spearman
    )
    assert left_result.sf06_liquidity_fragility.pre_depth_spearman == pytest.approx(
        right_result.sf06_liquidity_fragility.pre_depth_spearman
    )

    assert left_result.sf07_aggressor_sign_persistence.lag_acf == pytest.approx(
        right_result.sf07_aggressor_sign_persistence.lag_acf
    )
    assert left_result.sf07_aggressor_sign_persistence.mean_acf == pytest.approx(
        right_result.sf07_aggressor_sign_persistence.mean_acf
    )


def test_simulation_and_empirical_adapters_preserve_measurement_semantics() -> None:
    protocol = stylized_fact_validation_protocol()

    market_states = tuple(_market_state(period) for period in range(protocol.total_periods))

    orders = tuple(
        _aggressor_order(period)
        for period in range(
            protocol.burn_in_periods,
            protocol.total_periods,
        )
    )

    simulation_dataset = FinanceResearchDataset(
        market_states=market_states,
        orders=orders,
    )
    simulation_dataset.validate()

    simulation_sample = prepare_stylized_validation_simulation_sample(
        simulation_dataset,
        source_id="cross-source-simulation",
    )

    states_by_period = {state.period: state for state in market_states}

    empirical_intervals: list[EmpiricalMarketInterval] = []

    for index, period in enumerate(
        range(
            protocol.burn_in_periods - 1,
            protocol.total_periods,
        )
    ):
        state = states_by_period[period]

        assert state.mid_price is not None
        assert state.bid_depth is not None
        assert state.ask_depth is not None

        thin_depth = min(
            state.bid_depth,
            state.ask_depth,
        )

        aggressor_flow = (
            0.0 if period == protocol.burn_in_periods - 1 else (1.0 if period % 2 == 0 else -1.0)
        )

        empirical_intervals.append(
            EmpiricalMarketInterval(
                start_timestamp_ns=index * _INTERVAL_NS,
                end_timestamp_ns=(index + 1) * _INTERVAL_NS,
                mid_price=float(state.mid_price),
                aggressor_flow=aggressor_flow,
                thin_side_depth=float(thin_depth),
            )
        )

    empirical_sample = prepare_empirical_market_signature_sample(
        tuple(empirical_intervals),
        source_id="cross-source-empirical",
    )

    assert (
        simulation_sample.data.observation_count
        == empirical_sample.data.observation_count
        == protocol.analysis_horizon
    )

    assert simulation_sample.data.log_returns == pytest.approx(empirical_sample.data.log_returns)
    assert simulation_sample.data.aggressor_flow == empirical_sample.data.aggressor_flow
    assert simulation_sample.data.pre_interval_thin_side_depth == pytest.approx(
        empirical_sample.data.pre_interval_thin_side_depth
    )
    assert simulation_sample.data.relative_thin_side_depth_drop == pytest.approx(
        empirical_sample.data.relative_thin_side_depth_drop
    )

    assert simulation_sample.provenance.source_kind != empirical_sample.provenance.source_kind

    simulation_estimates = estimate_prepared_market_signatures(simulation_sample)
    empirical_estimates = estimate_prepared_market_signatures(empirical_sample)

    _assert_estimates_equivalent(
        simulation_estimates,
        empirical_estimates,
    )
