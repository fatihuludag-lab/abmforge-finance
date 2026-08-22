"""Unit tests for primitive market metrics."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from abmforge_finance.exceptions import InvalidMetricInputError
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
from abmforge_finance.recording import (
    DecisionRecord,
    FinanceResearchDataset,
    MarketStateRecord,
    OrderRecord,
    TradeRecord,
)


def _state(
    period: int,
    *,
    mid: Decimal | None,
    last: Decimal | None = None,
    fundamental: Decimal = Decimal("100"),
    spread: Decimal | None = Decimal("2"),
    bid_depth: Decimal = Decimal("3"),
    ask_depth: Decimal = Decimal("1"),
) -> MarketStateRecord:
    return MarketStateRecord(
        period=period,
        instrument_id="ACME",
        fundamental_value=fundamental,
        best_bid=None if mid is None or spread is None else mid - spread / Decimal("2"),
        best_ask=None if mid is None or spread is None else mid + spread / Decimal("2"),
        mid_price=mid,
        spread=spread,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        imbalance=None,
        order_count=0,
        last_trade_price=last,
        price_change=None,
        fee_balance=Decimal("0"),
    )


def _order(
    order_id: str,
    *,
    period: int,
    side: str,
    quantity: str,
    accepted: bool = True,
    executed: str = "0",
) -> OrderRecord:
    return OrderRecord(
        period=period,
        order_id=order_id,
        sequence_number=int(order_id.split("-")[-1]),
        agent_id=f"agent-{order_id}",
        instrument_id="ACME",
        side=side,
        order_type="market",
        quantity=Decimal(quantity),
        limit_price=None,
        submitted_at=period,
        time_in_force="ioc",
        accepted=accepted,
        executed_quantity=Decimal(executed),
        remaining_quantity=Decimal("0"),
        cancelled_quantity=Decimal("0"),
        rested=False,
        rejection_type=None if accepted else "Rejected",
        rejection_message=None,
    )


def test_metric_point_rejects_invalid_period() -> None:
    with pytest.raises(InvalidMetricInputError, match="period"):
        MetricPoint(-1, Decimal("1"))


def test_price_series_simple_returns_and_gap_semantics() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(3, mid=Decimal("121")),
            _state(0, mid=Decimal("100")),
            _state(1, mid=Decimal("110")),
        )
    )

    prices = market_prices(dataset)
    returns = simple_returns(dataset)

    assert prices == (
        MetricPoint(0, Decimal("100")),
        MetricPoint(1, Decimal("110")),
        MetricPoint(3, Decimal("121")),
    )
    assert returns == (
        MetricPoint(0, None),
        MetricPoint(1, Decimal("0.1")),
        MetricPoint(3, None),
    )


def test_missing_price_is_not_forward_filled() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(0, mid=Decimal("100")),
            _state(1, mid=None, spread=None),
            _state(2, mid=Decimal("121")),
        )
    )
    assert simple_returns(dataset) == (
        MetricPoint(0, None),
        MetricPoint(1, None),
        MetricPoint(2, None),
    )


def test_last_trade_basis_and_log_returns() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(0, mid=Decimal("99"), last=Decimal("100")),
            _state(1, mid=Decimal("100"), last=Decimal("110")),
        )
    )

    prices = market_prices(dataset, basis=MarketPriceBasis.LAST_TRADE)
    returns = log_returns(dataset, basis=MarketPriceBasis.LAST_TRADE)

    assert prices[1].value == Decimal("110")
    assert returns[0].value is None
    assert returns[1].value == pytest.approx(math.log(1.1))


def test_relative_spread_depth_and_fundamental_deviation_are_exact() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(
                0,
                mid=Decimal("105"),
                fundamental=Decimal("100"),
                spread=Decimal("2"),
                bid_depth=Decimal("3"),
                ask_depth=Decimal("7"),
            ),
        )
    )

    assert relative_spreads(dataset) == (MetricPoint(0, Decimal("2") / Decimal("105")),)
    assert total_depth(dataset) == (MetricPoint(0, Decimal("10")),)
    assert fundamental_deviation(dataset) == (MetricPoint(0, Decimal("5")),)
    assert relative_fundamental_deviation(dataset) == (MetricPoint(0, Decimal("0.05")),)


def test_decision_flow_separates_hold_and_directional_quantity() -> None:
    dataset = FinanceResearchDataset(
        market_states=(_state(0, mid=Decimal("100")), _state(1, mid=Decimal("100"))),
        decisions=(
            DecisionRecord(0, "a", "order", "buy", "market", Decimal("3"), None, "ioc"),
            DecisionRecord(0, "b", "order", "sell", "market", Decimal("1"), None, "ioc"),
            DecisionRecord(0, "c", "hold", None, None, None, None, None),
        ),
    )

    assert decision_flow_imbalance(dataset) == (
        MetricPoint(0, Decimal("0.5")),
        MetricPoint(1, None),
    )


def test_accepted_and_aggressor_executed_flow_are_distinct() -> None:
    dataset = FinanceResearchDataset(
        market_states=(_state(0, mid=Decimal("100")),),
        orders=(
            _order("o-1", period=0, side="buy", quantity="2", executed="1"),
            _order("o-2", period=0, side="sell", quantity="1", executed="0.5"),
            _order("o-3", period=0, side="buy", quantity="9", accepted=False),
        ),
    )

    assert accepted_order_flow_imbalance(dataset) == (MetricPoint(0, Decimal("1") / Decimal("3")),)
    assert aggressor_executed_flow_imbalance(dataset) == (
        MetricPoint(0, Decimal("1") / Decimal("3")),
    )


def test_trade_metrics_align_zero_and_undefined_no_trade_periods() -> None:
    dataset = FinanceResearchDataset(
        market_states=(_state(0, mid=Decimal("100")), _state(1, mid=Decimal("100"))),
        trades=(
            TradeRecord(
                0,
                "trade-1",
                1,
                "ACME",
                "buy-1",
                "sell-1",
                "buyer",
                "seller",
                "sell-1",
                "buy-1",
                Decimal("100"),
                Decimal("2"),
                0,
                Decimal("0"),
                Decimal("0"),
            ),
            TradeRecord(
                0,
                "trade-2",
                2,
                "ACME",
                "buy-2",
                "sell-2",
                "buyer",
                "seller",
                "sell-2",
                "buy-2",
                Decimal("101"),
                Decimal("1"),
                0,
                Decimal("0"),
                Decimal("0"),
            ),
        ),
    )

    assert trade_volume(dataset) == (
        MetricPoint(0, Decimal("3")),
        MetricPoint(1, Decimal("0")),
    )
    assert trade_count(dataset) == (MetricPoint(0, 2), MetricPoint(1, 0))
    assert trade_vwap(dataset) == (
        MetricPoint(0, Decimal("301") / Decimal("3")),
        MetricPoint(1, None),
    )


def test_metric_functions_reject_corrupt_direction_and_nonpositive_prices() -> None:
    corrupt_decision = FinanceResearchDataset(
        decisions=(
            DecisionRecord(0, "a", "order", "sideways", "market", Decimal("1"), None, "ioc"),
        )
    )
    with pytest.raises(InvalidMetricInputError, match="side"):
        decision_flow_imbalance(corrupt_decision)

    corrupt_price = FinanceResearchDataset(market_states=(_state(0, mid=Decimal("0")),))
    with pytest.raises(InvalidMetricInputError, match="positive"):
        market_prices(corrupt_price)


def test_price_basis_must_be_explicit_enum() -> None:
    with pytest.raises(TypeError, match="MarketPriceBasis"):
        market_prices(FinanceResearchDataset(), basis="mid")  # type: ignore[arg-type]
