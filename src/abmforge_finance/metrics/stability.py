"""Stability, synchronization, liquidity-stress, and tail-event metrics."""

from __future__ import annotations

import math
from decimal import Decimal

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.metrics.market import (
    fundamental_deviation,
    log_returns,
    market_prices,
    relative_fundamental_deviation,
    simple_returns,
    total_depth,
)
from abmforge_finance.metrics.types import MarketPriceBasis, MetricPoint
from abmforge_finance.recording import FinanceResearchDataset

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _validated(dataset: FinanceResearchDataset) -> FinanceResearchDataset:
    if not isinstance(dataset, FinanceResearchDataset):
        raise TypeError("dataset must be a FinanceResearchDataset")
    dataset.validate()
    return dataset


def _positive(value: Decimal, *, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= _ZERO:
        raise InvalidMetricInputError(f"{label} must be a positive finite Decimal")
    return value


def _window(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise InvalidMetricInputError("window must be a positive integer")
    return value


def _fraction(value: Decimal, *, label: str) -> Decimal:
    value = _positive(value, label=label)
    if value > _ONE:
        raise InvalidMetricInputError(f"{label} must be less than or equal to 1")
    return value


def _axis(dataset: FinanceResearchDataset, observed: set[int]) -> tuple[int, ...]:
    periods = {row.period for row in dataset.market_states}
    periods.update(observed)
    return tuple(sorted(periods))


def _bucket(side: str) -> int:
    if side == "buy":
        return 0
    if side == "sell":
        return 1
    raise InvalidMetricInputError(f"unsupported directional side: {side!r}")


def _concentration(buys: int, sells: int) -> Decimal | None:
    total = buys + sells
    return None if total == 0 else Decimal(abs(buys - sells)) / Decimal(total)


def realized_volatility(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> float | None:
    """Return unannualized ``sqrt(sum(log_return**2))`` for the full series."""

    returns = log_returns(dataset, basis=basis)
    if len(returns) < 2:
        return None
    values = tuple(point.value for point in returns[1:])
    if any(value is None for value in values):
        return None
    defined = tuple(value for value in values if value is not None)
    return math.sqrt(sum(value * value for value in defined))


def rolling_realized_volatility(
    dataset: FinanceResearchDataset,
    *,
    window: int,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[float], ...]:
    """Return trailing unannualized realized volatility over ``window`` returns."""

    window = _window(window)
    returns = log_returns(dataset, basis=basis)
    output: list[MetricPoint[float]] = []
    for index, point in enumerate(returns):
        start = index - window + 1
        values = () if start < 1 else tuple(item.value for item in returns[start : index + 1])
        if len(values) != window or any(value is None for value in values):
            output.append(MetricPoint(point.period, None))
            continue
        defined = tuple(value for value in values if value is not None)
        output.append(MetricPoint(point.period, math.sqrt(sum(value * value for value in defined))))
    return tuple(output)


def drawdowns(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return exact ``P_t / running_peak_t - 1`` drawdown."""

    peak: Decimal | None = None
    output: list[MetricPoint[Decimal]] = []
    for point in market_prices(dataset, basis=basis):
        if point.value is None:
            output.append(MetricPoint(point.period, None))
            continue
        peak = point.value if peak is None or point.value > peak else peak
        output.append(MetricPoint(point.period, point.value / peak - _ONE))
    return tuple(output)


def maximum_drawdown(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> Decimal | None:
    """Return the most negative defined drawdown."""

    values = tuple(
        point.value for point in drawdowns(dataset, basis=basis) if point.value is not None
    )
    return None if not values else min(values)


def depth_depletion(
    dataset: FinanceResearchDataset,
    *,
    reference_depth: Decimal,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return ``1 - displayed_depth / reference_depth``."""

    reference = _positive(reference_depth, label="reference depth")
    return tuple(
        MetricPoint(point.period, _ONE - point.value / reference)
        for point in total_depth(dataset)
        if point.value is not None
    )


def spread_amplification(
    dataset: FinanceResearchDataset,
    *,
    reference_spread: Decimal,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return ``spread / reference_spread - 1``."""

    dataset = _validated(dataset)
    reference = _positive(reference_spread, label="reference spread")
    output: list[MetricPoint[Decimal]] = []
    for row in sorted(dataset.market_states, key=lambda item: item.period):
        if row.spread is None:
            output.append(MetricPoint(row.period, None))
            continue
        if not row.spread.is_finite() or row.spread < _ZERO:
            raise InvalidMetricInputError("spread must be a non-negative finite Decimal")
        output.append(MetricPoint(row.period, row.spread / reference - _ONE))
    return tuple(output)


def absolute_fundamental_deviation(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return absolute price-minus-fundamental dislocation."""

    return tuple(
        MetricPoint(point.period, None if point.value is None else abs(point.value))
        for point in fundamental_deviation(dataset, basis=basis)
    )


def relative_absolute_fundamental_deviation(
    dataset: FinanceResearchDataset,
    *,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return absolute relative price/fundamental dislocation."""

    return tuple(
        MetricPoint(point.period, None if point.value is None else abs(point.value))
        for point in relative_fundamental_deviation(dataset, basis=basis)
    )


def decision_sign_concentration(
    dataset: FinanceResearchDataset,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return ``abs(N_buy-N_sell)/(N_buy+N_sell)`` for ORDER decisions."""

    dataset = _validated(dataset)
    counts: dict[int, list[int]] = {}
    observed: set[int] = set()
    for row in dataset.decisions:
        observed.add(row.period)
        counts.setdefault(row.period, [0, 0])
        if row.kind == "hold":
            if row.side is not None or row.quantity is not None:
                raise InvalidMetricInputError("hold decision carries directional fields")
            continue
        if row.kind != "order" or row.side is None or row.quantity is None:
            raise InvalidMetricInputError("order decision is missing side or quantity")
        _positive(row.quantity, label="decision quantity")
        counts[row.period][_bucket(row.side)] += 1
    return tuple(
        MetricPoint(period, _concentration(*counts.get(period, [0, 0])))
        for period in _axis(dataset, observed)
    )


def accepted_order_sign_concentration(
    dataset: FinanceResearchDataset,
) -> tuple[MetricPoint[Decimal], ...]:
    """Return unweighted same-direction concentration among accepted orders."""

    dataset = _validated(dataset)
    counts: dict[int, list[int]] = {}
    observed: set[int] = set()
    for row in dataset.orders:
        observed.add(row.period)
        counts.setdefault(row.period, [0, 0])
        if not row.accepted:
            continue
        _positive(row.quantity, label="accepted order quantity")
        counts[row.period][_bucket(row.side)] += 1
    return tuple(
        MetricPoint(period, _concentration(*counts.get(period, [0, 0])))
        for period in _axis(dataset, observed)
    )


def extreme_return_breaches(
    dataset: FinanceResearchDataset,
    *,
    threshold: Decimal,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[bool], ...]:
    """Flag absolute simple returns at or beyond an explicit threshold."""

    threshold = _positive(threshold, label="return threshold")
    return tuple(
        MetricPoint(point.period, None if point.value is None else abs(point.value) >= threshold)
        for point in simple_returns(dataset, basis=basis)
    )


def downside_return_breaches(
    dataset: FinanceResearchDataset,
    *,
    threshold: Decimal,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[bool], ...]:
    """Flag simple returns at or below ``-threshold``."""

    threshold = _positive(threshold, label="return threshold")
    return tuple(
        MetricPoint(point.period, None if point.value is None else point.value <= -threshold)
        for point in simple_returns(dataset, basis=basis)
    )


def drawdown_breaches(
    dataset: FinanceResearchDataset,
    *,
    threshold: Decimal,
    basis: MarketPriceBasis = MarketPriceBasis.MID,
) -> tuple[MetricPoint[bool], ...]:
    """Flag drawdowns at or below ``-threshold`` for ``0 < threshold <= 1``."""

    threshold = _fraction(threshold, label="drawdown threshold")
    return tuple(
        MetricPoint(point.period, None if point.value is None else point.value <= -threshold)
        for point in drawdowns(dataset, basis=basis)
    )
