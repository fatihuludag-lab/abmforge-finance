"""Property tests for deterministic market-metric semantics."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance.metrics import MetricPoint, decision_flow_imbalance, simple_returns
from abmforge_finance.recording import DecisionRecord, FinanceResearchDataset, MarketStateRecord


def _state(period: int, price: Decimal) -> MarketStateRecord:
    return MarketStateRecord(
        period,
        "ACME",
        Decimal("100"),
        price - Decimal("1"),
        price + Decimal("1"),
        price,
        Decimal("2"),
        Decimal("1"),
        Decimal("1"),
        Decimal("0"),
        0,
        None,
        None,
        Decimal("0"),
    )


@given(order=st.permutations((0, 1, 2)))
def test_price_metrics_are_input_tuple_order_independent(order: list[int]) -> None:
    rows = {
        0: _state(0, Decimal("100")),
        1: _state(1, Decimal("105")),
        2: _state(2, Decimal("110.25")),
    }
    dataset = FinanceResearchDataset(market_states=tuple(rows[index] for index in order))
    assert simple_returns(dataset) == (
        # First period is undefined; the next two are exactly five percent.
        # Decimal arithmetic keeps these algebraic values exact.
        MetricPoint(0, None),
        MetricPoint(1, Decimal("0.05")),
        MetricPoint(2, Decimal("0.05")),
    )


@given(order=st.permutations(("a", "b", "c")))
def test_decision_imbalance_is_agent_row_order_independent(order: list[str]) -> None:
    rows = {
        "a": DecisionRecord(0, "a", "order", "buy", "market", Decimal("3"), None, "ioc"),
        "b": DecisionRecord(0, "b", "order", "sell", "market", Decimal("1"), None, "ioc"),
        "c": DecisionRecord(0, "c", "hold", None, None, None, None, None),
    }
    dataset = FinanceResearchDataset(decisions=tuple(rows[agent_id] for agent_id in order))
    result = decision_flow_imbalance(dataset)
    assert result[0].value == Decimal("0.5")
