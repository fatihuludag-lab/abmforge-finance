"""Tests for directional liquidity-stress metrics."""

from decimal import Decimal

from abmforge_finance.metrics import (
    depth_asymmetry,
    thin_side_depletion,
    thin_side_depth,
)
from abmforge_finance.recording import FinanceResearchDataset, MarketStateRecord


def _state(period: int, bid: str, ask: str) -> MarketStateRecord:
    return MarketStateRecord(
        period=period,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
        best_bid=Decimal("99"),
        best_ask=Decimal("101"),
        mid_price=Decimal("100"),
        spread=Decimal("2"),
        bid_depth=Decimal(bid),
        ask_depth=Decimal(ask),
        imbalance=None,
        order_count=2,
        last_trade_price=None,
        price_change=None,
        fee_balance=Decimal("0"),
    )


def test_thin_side_depth_and_asymmetry_capture_directional_stress() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(0, "8", "2"),
            _state(1, "5", "5"),
            _state(2, "0", "0"),
        )
    )

    assert tuple(point.value for point in thin_side_depth(dataset)) == (
        Decimal("2"),
        Decimal("5"),
        Decimal("0"),
    )
    assert tuple(point.value for point in depth_asymmetry(dataset)) == (
        Decimal("0.6"),
        Decimal("0"),
        None,
    )


def test_thin_side_depletion_uses_explicit_side_reference() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(0, "8", "2"),
            _state(1, "5", "5"),
        )
    )

    assert tuple(
        point.value
        for point in thin_side_depletion(
            dataset,
            reference_side_depth=Decimal("10"),
        )
    ) == (Decimal("0.8"), Decimal("0.5"))
