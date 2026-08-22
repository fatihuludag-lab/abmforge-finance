"""Property tests for stability metrics."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance.metrics import MetricPoint, decision_sign_concentration, drawdowns
from abmforge_finance.recording import DecisionRecord, FinanceResearchDataset, MarketStateRecord


def _state(period: int, price: Decimal) -> MarketStateRecord:
    return MarketStateRecord(
        period,
        "ACME",
        Decimal("100"),
        price - 1,
        price + 1,
        price,
        Decimal("2"),
        Decimal("1"),
        Decimal("1"),
        Decimal("0"),
        0,
        price,
        None,
        Decimal("0"),
    )


@given(scale=st.integers(min_value=1, max_value=1000))
def test_drawdown_is_invariant_to_positive_price_scale(scale: int) -> None:
    prices = (Decimal("100"), Decimal("120"), Decimal("90"), Decimal("108"))
    left = FinanceResearchDataset(market_states=tuple(_state(i, p) for i, p in enumerate(prices)))
    right = FinanceResearchDataset(
        market_states=tuple(_state(i, p * Decimal(scale)) for i, p in enumerate(prices))
    )
    assert drawdowns(left) == drawdowns(right)


@given(order=st.permutations(("a", "b", "c", "d")))
def test_sign_concentration_is_row_order_independent(order: list[str]) -> None:
    rows = {
        "a": DecisionRecord(0, "a", "order", "buy", "market", Decimal("3"), None, "ioc"),
        "b": DecisionRecord(0, "b", "order", "buy", "market", Decimal("1"), None, "ioc"),
        "c": DecisionRecord(0, "c", "order", "sell", "market", Decimal("7"), None, "ioc"),
        "d": DecisionRecord(0, "d", "hold", None, None, None, None, None),
    }
    dataset = FinanceResearchDataset(decisions=tuple(rows[key] for key in order))
    assert decision_sign_concentration(dataset) == (MetricPoint(0, Decimal("1") / Decimal("3")),)
