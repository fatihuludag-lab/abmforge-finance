"""Public API tests for primitive market metrics."""

from abmforge_finance.metrics import (
    MarketPriceBasis,
    MetricPoint,
    accepted_order_flow_imbalance,
    aggressor_executed_flow_imbalance,
    decision_flow_imbalance,
    fundamental_deviation,
    log_returns,
    market_prices,
    relative_fundamental_deviation,
    relative_spreads,
    simple_returns,
    total_depth,
    trade_count,
    trade_volume,
    trade_vwap,
)


def test_metrics_public_api() -> None:
    assert MarketPriceBasis.MID.value == "mid"
    assert MetricPoint is not None
    assert all(
        callable(value)
        for value in (
            market_prices,
            simple_returns,
            log_returns,
            relative_spreads,
            total_depth,
            fundamental_deviation,
            relative_fundamental_deviation,
            decision_flow_imbalance,
            accepted_order_flow_imbalance,
            aggressor_executed_flow_imbalance,
            trade_volume,
            trade_count,
            trade_vwap,
        )
    )
