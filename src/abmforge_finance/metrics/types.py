"""Typed values for deterministic finance market metrics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from abmforge_finance.exceptions import InvalidMetricInputError

MetricValue = TypeVar("MetricValue")


class MarketPriceBasis(str, Enum):
    """Explicit market-price source used by price-based metrics."""

    MID = "mid"
    LAST_TRADE = "last_trade"


@dataclass(frozen=True, slots=True)
class MetricPoint(Generic[MetricValue]):
    """One period-aligned metric value; ``None`` means undefined, not zero."""

    period: int
    value: MetricValue | None

    def __post_init__(self) -> None:
        if not isinstance(self.period, int) or isinstance(self.period, bool) or self.period < 0:
            raise InvalidMetricInputError("metric period must be a non-negative integer")
