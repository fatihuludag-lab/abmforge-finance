"""Pure market-metric functions over :class:`FinanceResearchDataset`."""

from __future__ import annotations

import math
from decimal import Decimal

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.metrics.types import MarketPriceBasis, MetricPoint
from abmforge_finance.recording import FinanceResearchDataset, MarketStateRecord

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _dataset(dataset: FinanceResearchDataset) -> FinanceResearchDataset:
    if not isinstance(dataset, FinanceResearchDataset):
        raise TypeError("dataset must be a FinanceResearchDataset")
    dataset.validate()
    return dataset


def _price(row: MarketStateRecord, basis: MarketPriceBasis) -> Decimal | None:
    if basis is MarketPriceBasis.MID:
        return row.mid_price
    if basis is MarketPriceBasis.LAST_TRADE:
        return row.last_trade_price
    raise TypeError("basis must be a MarketPriceBasis")


def _positive(value: Decimal, *, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= _ZERO:
        raise InvalidMetricInputError(f"{label} must be a positive finite Decimal")
    return value


def _non_negative(value: Decimal, *, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < _ZERO:
        raise InvalidMetricInputError(f"{label} must be a non-negative finite Decimal")
    return value


def _period_axis(dataset: FinanceResearchDataset, observed: set[int]) -> tuple[int, ...]:
    periods = {row.period for row in dataset.market_states}
    periods.update(observed)
    return tuple(sorted(periods))


def _side_bucket(side: str) -> int:
    if side == "buy":
        return 0
    if side == "sell":
        return 1
    raise InvalidMetricInputError(f"unsupported directional side: {side!r}")


def _imbalance(buy: Decimal, sell: Decimal) -> Decimal | None:
    denominator = buy + sell
    if denominator == _ZERO:
        return None
    return (buy - sell) / denominator


def market_prices(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return the selected market price for each recorded market-state period."""

    dataset = _dataset(dataset)
    if not isinstance(basis, MarketPriceBasis):
        raise TypeError("basis must be a MarketPriceBasis")
    points: list[MetricPoint[Decimal]] = []
    for row in sorted(dataset.market_states, key=lambda item: item.period):
        value = _price(row, basis)
        if value is not None:
            value = _positive(value, label=f"{basis.value} price")
        points.append(MetricPoint(row.period, value))
    return tuple(points)


def simple_returns(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return exact adjacent-period simple returns ``P_t / P_(t-1) - 1``.

    The first point, a missing endpoint, or a non-consecutive period gap yields
    ``None``. Prices are never forward-filled.
    """

    prices = market_prices(dataset, basis=basis)
    output: list[MetricPoint[Decimal]] = []
    previous: MetricPoint[Decimal] | None = None
    for point in prices:
        value: Decimal | None = None
        if (
            previous is not None
            and point.period == previous.period + 1
            and previous.value is not None
            and point.value is not None
        ):
            value = point.value / previous.value - _ONE
        output.append(MetricPoint(point.period, value))
        previous = point
    return tuple(output)


def log_returns(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[float], ...]:
    """Return adjacent-period natural-log returns.

    Log returns are statistical derived values and therefore use finite Python
    ``float`` values. Exact prices remain available in the research dataset.
    """

    prices = market_prices(dataset, basis=basis)
    output: list[MetricPoint[float]] = []
    previous: MetricPoint[Decimal] | None = None
    for point in prices:
        value: float | None = None
        if (
            previous is not None
            and point.period == previous.period + 1
            and previous.value is not None
            and point.value is not None
        ):
            ratio = float(point.value / previous.value)
            if not math.isfinite(ratio) or ratio <= 0.0:
                raise InvalidMetricInputError("price ratio must map to a positive finite float")
            value = math.log(ratio)
        output.append(MetricPoint(point.period, value))
        previous = point
    return tuple(output)


def relative_spreads(dataset: FinanceResearchDataset) -> tuple[MetricPoint[Decimal], ...]:
    """Return ``spread / mid_price`` for each market-state period."""

    dataset = _dataset(dataset)
    output: list[MetricPoint[Decimal]] = []
    for row in sorted(dataset.market_states, key=lambda item: item.period):
        value: Decimal | None = None
        if row.spread is not None or row.mid_price is not None:
            if row.spread is None or row.mid_price is None:
                value = None
            else:
                spread = _non_negative(row.spread, label="spread")
                mid = _positive(row.mid_price, label="mid price")
                value = spread / mid
        output.append(MetricPoint(row.period, value))
    return tuple(output)


def total_depth(dataset: FinanceResearchDataset) -> tuple[MetricPoint[Decimal], ...]:
    """Return exact displayed bid-plus-ask depth."""

    dataset = _dataset(dataset)
    output = []
    for row in sorted(dataset.market_states, key=lambda item: item.period):
        bid = _non_negative(row.bid_depth, label="bid depth")
        ask = _non_negative(row.ask_depth, label="ask depth")
        output.append(MetricPoint(row.period, bid + ask))
    return tuple(output)


def fundamental_deviation(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return signed ``market_price - fundamental_value``."""

    dataset = _dataset(dataset)
    if not isinstance(basis, MarketPriceBasis):
        raise TypeError("basis must be a MarketPriceBasis")
    output = []
    for row in sorted(dataset.market_states, key=lambda item: item.period):
        fundamental = _positive(row.fundamental_value, label="fundamental value")
        price = _price(row, basis)
        if price is not None:
            price = _positive(price, label=f"{basis.value} price")
        output.append(MetricPoint(row.period, None if price is None else price - fundamental))
    return tuple(output)


def relative_fundamental_deviation(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return signed ``market_price / fundamental_value - 1``."""

    dataset = _dataset(dataset)
    if not isinstance(basis, MarketPriceBasis):
        raise TypeError("basis must be a MarketPriceBasis")
    output = []
    for row in sorted(dataset.market_states, key=lambda item: item.period):
        fundamental = _positive(row.fundamental_value, label="fundamental value")
        price = _price(row, basis)
        if price is not None:
            price = _positive(price, label=f"{basis.value} price")
        output.append(
            MetricPoint(
                row.period,
                None if price is None else price / fundamental - _ONE,
            )
        )
    return tuple(output)


def decision_flow_imbalance(
    dataset: FinanceResearchDataset,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return quantity-weighted directional policy imbalance by period.

    ``HOLD`` decisions contribute zero directional quantity. For order decisions,
    BUY quantity is positive and SELL quantity is negative. The normalized result
    is ``(Q_buy - Q_sell) / (Q_buy + Q_sell)`` and is ``None`` when no directional
    quantity exists.
    """

    dataset = _dataset(dataset)
    totals: dict[int, list[Decimal]] = {}
    observed: set[int] = set()
    for row in dataset.decisions:
        observed.add(row.period)
        totals.setdefault(row.period, [_ZERO, _ZERO])
        if row.kind == "hold":
            if row.side is not None or row.quantity is not None:
                raise InvalidMetricInputError("hold decision carries directional fields")
            continue
        if row.kind != "order" or row.side is None or row.quantity is None:
            raise InvalidMetricInputError("order decision is missing side or quantity")
        quantity = _positive(row.quantity, label="decision quantity")
        totals[row.period][_side_bucket(row.side)] += quantity

    return tuple(
        MetricPoint(period, _imbalance(*totals.get(period, [_ZERO, _ZERO])))
        for period in _period_axis(dataset, observed)
    )


def accepted_order_flow_imbalance(
    dataset: FinanceResearchDataset,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return normalized submitted quantity for accepted orders only."""

    dataset = _dataset(dataset)
    totals: dict[int, list[Decimal]] = {}
    observed: set[int] = set()
    for row in dataset.orders:
        observed.add(row.period)
        totals.setdefault(row.period, [_ZERO, _ZERO])
        if not row.accepted:
            continue
        quantity = _positive(row.quantity, label="accepted order quantity")
        totals[row.period][_side_bucket(row.side)] += quantity

    return tuple(
        MetricPoint(period, _imbalance(*totals.get(period, [_ZERO, _ZERO])))
        for period in _period_axis(dataset, observed)
    )


def aggressor_executed_flow_imbalance(
    dataset: FinanceResearchDataset,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return normalized incoming-order executed quantity by side.

    This measures the directional flow initiated by submitted orders at their
    submission event. It is not total market volume and does not attribute later
    passive fills back to the original resting-order submission period.
    """

    dataset = _dataset(dataset)
    totals: dict[int, list[Decimal]] = {}
    observed: set[int] = set()
    for row in dataset.orders:
        observed.add(row.period)
        totals.setdefault(row.period, [_ZERO, _ZERO])
        if not row.accepted:
            continue
        quantity = _non_negative(row.executed_quantity, label="executed order quantity")
        if quantity == _ZERO:
            continue
        totals[row.period][_side_bucket(row.side)] += quantity

    return tuple(
        MetricPoint(period, _imbalance(*totals.get(period, [_ZERO, _ZERO])))
        for period in _period_axis(dataset, observed)
    )


def trade_volume(dataset: FinanceResearchDataset) -> tuple[MetricPoint[Decimal], ...]:
    """Return exact executed trade quantity by period; no-trade periods are zero."""

    dataset = _dataset(dataset)
    totals: dict[int, Decimal] = {}
    observed: set[int] = set()
    for row in dataset.trades:
        observed.add(row.period)
        quantity = _positive(row.quantity, label="trade quantity")
        totals[row.period] = totals.get(row.period, _ZERO) + quantity

    return tuple(
        MetricPoint(period, totals.get(period, _ZERO)) for period in _period_axis(dataset, observed)
    )


def trade_count(dataset: FinanceResearchDataset) -> tuple[MetricPoint[int], ...]:
    """Return committed trade count by period; no-trade periods are zero."""

    dataset = _dataset(dataset)
    counts: dict[int, int] = {}
    observed: set[int] = set()
    for row in dataset.trades:
        observed.add(row.period)
        counts[row.period] = counts.get(row.period, 0) + 1

    return tuple(
        MetricPoint(period, counts.get(period, 0)) for period in _period_axis(dataset, observed)
    )


def trade_vwap(dataset: FinanceResearchDataset) -> tuple[MetricPoint[Decimal], ...]:
    """Return exact quantity-weighted average trade price; no-trade periods are undefined."""

    dataset = _dataset(dataset)
    notional: dict[int, Decimal] = {}
    volume: dict[int, Decimal] = {}
    observed: set[int] = set()
    for row in dataset.trades:
        observed.add(row.period)
        price = _positive(row.price, label="trade price")
        quantity = _positive(row.quantity, label="trade quantity")
        notional[row.period] = notional.get(row.period, _ZERO) + price * quantity
        volume[row.period] = volume.get(row.period, _ZERO) + quantity

    return tuple(
        MetricPoint(
            period,
            None if volume.get(period, _ZERO) == _ZERO else notional[period] / volume[period],
        )
        for period in _period_axis(dataset, observed)
    )
