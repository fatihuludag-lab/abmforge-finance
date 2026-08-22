"""Tests for stability, synchronization, liquidity-stress, and tail metrics."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.metrics import (
    MetricPoint,
    absolute_fundamental_deviation,
    accepted_order_sign_concentration,
    decision_sign_concentration,
    depth_depletion,
    downside_return_breaches,
    drawdown_breaches,
    drawdowns,
    extreme_return_breaches,
    maximum_drawdown,
    realized_volatility,
    relative_absolute_fundamental_deviation,
    rolling_realized_volatility,
    spread_amplification,
)
from abmforge_finance.recording import (
    DecisionRecord,
    FinanceResearchDataset,
    MarketStateRecord,
    OrderRecord,
)


def _state(
    period: int,
    price: Decimal | None,
    *,
    fundamental: str = "100",
    spread: Decimal | None = Decimal("2"),
    bid: str = "50",
    ask: str = "50",
) -> MarketStateRecord:
    return MarketStateRecord(
        period,
        "ACME",
        Decimal(fundamental),
        None if price is None or spread is None else price - spread / 2,
        None if price is None or spread is None else price + spread / 2,
        price,
        spread,
        Decimal(bid),
        Decimal(ask),
        None,
        0,
        price,
        None,
        Decimal("0"),
    )


def _order(number: int, side: str, accepted: bool) -> OrderRecord:
    return OrderRecord(
        0,
        f"o-{number}",
        number,
        f"a-{number}",
        "ACME",
        side,
        "market",
        Decimal("1"),
        None,
        0,
        "ioc",
        accepted,
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        False,
        None if accepted else "Rejected",
        None,
    )


def test_realized_and_rolling_volatility() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(0, Decimal("100")),
            _state(1, Decimal("110")),
            _state(2, Decimal("99")),
        )
    )
    r1, r2 = math.log(1.1), math.log(0.9)
    expected = math.sqrt(r1 * r1 + r2 * r2)
    assert realized_volatility(dataset) == pytest.approx(expected)
    rolling = rolling_realized_volatility(dataset, window=2)
    assert rolling[:2] == (MetricPoint(0, None), MetricPoint(1, None))
    assert rolling[2].value == pytest.approx(expected)


def test_volatility_missing_gap_and_short_series_semantics() -> None:
    short = FinanceResearchDataset(market_states=(_state(0, Decimal("100")),))
    assert realized_volatility(short) is None
    gap = FinanceResearchDataset(
        market_states=(
            _state(0, Decimal("100")),
            _state(2, Decimal("100")),
            _state(3, Decimal("110")),
            _state(4, Decimal("121")),
        )
    )
    assert realized_volatility(gap) is None
    rolling = rolling_realized_volatility(gap, window=2)
    assert rolling[2].value is None
    assert rolling[3].value == pytest.approx(math.sqrt(2 * math.log(1.1) ** 2))


def test_drawdowns_missing_price_and_maximum() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(0, Decimal("100")),
            _state(1, Decimal("120")),
            _state(2, None, spread=None),
            _state(3, Decimal("90")),
            _state(4, Decimal("108")),
        )
    )
    assert drawdowns(dataset) == (
        MetricPoint(0, Decimal("0")),
        MetricPoint(1, Decimal("0")),
        MetricPoint(2, None),
        MetricPoint(3, Decimal("-0.25")),
        MetricPoint(4, Decimal("-0.10")),
    )
    assert maximum_drawdown(dataset) == Decimal("-0.25")
    assert maximum_drawdown(FinanceResearchDataset()) is None


def test_liquidity_stress_uses_explicit_references() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(0, Decimal("100"), spread=Decimal("2"), bid="50", ask="50"),
            _state(1, Decimal("100"), spread=Decimal("3"), bid="30", ask="50"),
            _state(2, Decimal("100"), spread=Decimal("4"), bid="25", ask="25"),
        )
    )
    assert depth_depletion(dataset, reference_depth=Decimal("100")) == (
        MetricPoint(0, Decimal("0")),
        MetricPoint(1, Decimal("0.2")),
        MetricPoint(2, Decimal("0.5")),
    )
    assert spread_amplification(dataset, reference_spread=Decimal("2")) == (
        MetricPoint(0, Decimal("0")),
        MetricPoint(1, Decimal("0.5")),
        MetricPoint(2, Decimal("1")),
    )


def test_missing_spread_and_invalid_spread() -> None:
    missing = FinanceResearchDataset(market_states=(_state(0, None, spread=None),))
    assert spread_amplification(missing, reference_spread=Decimal("2")) == (MetricPoint(0, None),)
    bad = FinanceResearchDataset(market_states=(_state(0, Decimal("100"), spread=Decimal("-1")),))
    with pytest.raises(InvalidMetricInputError, match="spread"):
        spread_amplification(bad, reference_spread=Decimal("2"))


def test_absolute_dislocation_is_exact() -> None:
    dataset = FinanceResearchDataset(
        market_states=(_state(0, Decimal("95")), _state(1, Decimal("110")))
    )
    assert absolute_fundamental_deviation(dataset) == (
        MetricPoint(0, Decimal("5")),
        MetricPoint(1, Decimal("10")),
    )
    assert relative_absolute_fundamental_deviation(dataset) == (
        MetricPoint(0, Decimal("0.05")),
        MetricPoint(1, Decimal("0.1")),
    )


def test_decision_and_accepted_order_sign_concentration() -> None:
    dataset = FinanceResearchDataset(
        market_states=(_state(0, Decimal("100")), _state(1, Decimal("100"))),
        decisions=(
            DecisionRecord(0, "a", "order", "buy", "market", Decimal("100"), None, "ioc"),
            DecisionRecord(0, "b", "order", "buy", "market", Decimal("1"), None, "ioc"),
            DecisionRecord(0, "c", "order", "sell", "market", Decimal("1"), None, "ioc"),
            DecisionRecord(0, "d", "hold", None, None, None, None, None),
        ),
        orders=(
            _order(1, "buy", True),
            _order(2, "buy", True),
            _order(3, "sell", True),
            _order(4, "sell", False),
        ),
    )
    expected = Decimal("1") / Decimal("3")
    assert decision_sign_concentration(dataset) == (MetricPoint(0, expected), MetricPoint(1, None))
    assert accepted_order_sign_concentration(dataset) == (
        MetricPoint(0, expected),
        MetricPoint(1, None),
    )


def test_explicit_tail_and_drawdown_breaches() -> None:
    dataset = FinanceResearchDataset(
        market_states=(
            _state(0, Decimal("100")),
            _state(1, Decimal("90")),
            _state(2, Decimal("108")),
        )
    )
    assert downside_return_breaches(dataset, threshold=Decimal("0.10")) == (
        MetricPoint(0, None),
        MetricPoint(1, True),
        MetricPoint(2, False),
    )
    assert extreme_return_breaches(dataset, threshold=Decimal("0.15")) == (
        MetricPoint(0, None),
        MetricPoint(1, False),
        MetricPoint(2, True),
    )
    assert drawdown_breaches(dataset, threshold=Decimal("0.10")) == (
        MetricPoint(0, False),
        MetricPoint(1, True),
        MetricPoint(2, False),
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda d: rolling_realized_volatility(d, window=0),
        lambda d: depth_depletion(d, reference_depth=Decimal("0")),
        lambda d: spread_amplification(d, reference_spread=Decimal("0")),
        lambda d: extreme_return_breaches(d, threshold=Decimal("0")),
        lambda d: drawdown_breaches(d, threshold=Decimal("1.1")),
    ],
)
def test_invalid_parameters(call) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InvalidMetricInputError):
        call(FinanceResearchDataset(market_states=(_state(0, Decimal("100")),)))


def test_corrupt_directional_rows_and_dataset_type_are_rejected() -> None:
    bad_hold = FinanceResearchDataset(
        decisions=(DecisionRecord(0, "a", "hold", "buy", None, Decimal("1"), None, None),)
    )
    with pytest.raises(InvalidMetricInputError, match="hold"):
        decision_sign_concentration(bad_hold)
    bad_order = FinanceResearchDataset(
        decisions=(DecisionRecord(0, "a", "order", None, "market", None, None, "ioc"),)
    )
    with pytest.raises(InvalidMetricInputError, match="missing"):
        decision_sign_concentration(bad_order)
    bad_side = FinanceResearchDataset(orders=(_order(1, "sideways", True),))
    with pytest.raises(InvalidMetricInputError, match="side"):
        accepted_order_sign_concentration(bad_side)
    with pytest.raises(TypeError):
        decision_sign_concentration(object())  # type: ignore[arg-type]
