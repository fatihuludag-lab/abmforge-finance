"""Source-neutral empirical-market adapter for Phase 11 signatures."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.stylized_pipeline import (
    MarketSignatureInput,
    MarketSignatureInputProvenance,
    MarketSignatureSourceKind,
    PreparedMarketSignatureSample,
)
from abmforge_finance.study.stylized_protocol import (
    stylized_fact_validation_protocol,
)

EMPIRICAL_MARKET_SIGNATURE_PREPARATION_ID = "phase11-empirical-interval-v1"


def _finite_real(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidMetricInputError(f"{label} must be a finite real number")

    number = float(value)

    if not math.isfinite(number):
        raise InvalidMetricInputError(f"{label} must be a finite real number")

    return number


def _timestamp_ns(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidMetricInputError(f"{label} must be a non-negative integer")

    if value < 0:
        raise InvalidMetricInputError(f"{label} must be a non-negative integer")

    return value


@dataclass(frozen=True, slots=True)
class EmpiricalMarketInterval:
    """One completed, source-neutral empirical market interval."""

    start_timestamp_ns: int
    end_timestamp_ns: int
    mid_price: float
    aggressor_flow: float
    thin_side_depth: float

    def __post_init__(self) -> None:
        start = _timestamp_ns(
            self.start_timestamp_ns,
            label="start_timestamp_ns",
        )
        end = _timestamp_ns(
            self.end_timestamp_ns,
            label="end_timestamp_ns",
        )

        if end <= start:
            raise InvalidMetricInputError(
                "end_timestamp_ns must be greater than start_timestamp_ns"
            )

        mid_price = _finite_real(
            self.mid_price,
            label="mid_price",
        )
        aggressor_flow = _finite_real(
            self.aggressor_flow,
            label="aggressor_flow",
        )
        thin_side_depth = _finite_real(
            self.thin_side_depth,
            label="thin_side_depth",
        )

        if mid_price <= 0.0:
            raise InvalidMetricInputError("mid_price must be positive")

        if thin_side_depth < 0.0:
            raise InvalidMetricInputError("thin_side_depth must be non-negative")

        object.__setattr__(
            self,
            "start_timestamp_ns",
            start,
        )
        object.__setattr__(
            self,
            "end_timestamp_ns",
            end,
        )
        object.__setattr__(
            self,
            "mid_price",
            mid_price,
        )
        object.__setattr__(
            self,
            "aggressor_flow",
            aggressor_flow,
        )
        object.__setattr__(
            self,
            "thin_side_depth",
            thin_side_depth,
        )


def prepare_empirical_market_signature_sample(
    intervals: tuple[EmpiricalMarketInterval, ...],
    *,
    source_id: str,
) -> PreparedMarketSignatureSample:
    """Prepare aligned empirical intervals for shared estimation."""

    if not isinstance(intervals, tuple):
        raise TypeError("intervals must be a tuple of EmpiricalMarketInterval")

    protocol = stylized_fact_validation_protocol()

    minimum_intervals = protocol.maximum_acf_lag + 2

    if len(intervals) < minimum_intervals:
        raise InvalidMetricInputError(
            f"empirical preparation requires at least {minimum_intervals} intervals"
        )

    for index, interval in enumerate(intervals):
        if not isinstance(interval, EmpiricalMarketInterval):
            raise TypeError(f"intervals[{index}] must be an EmpiricalMarketInterval")

    interval_width = intervals[0].end_timestamp_ns - intervals[0].start_timestamp_ns

    for previous, current in pairwise(intervals):
        if current.start_timestamp_ns != previous.end_timestamp_ns:
            raise InvalidMetricInputError(
                "empirical intervals must be contiguous without gaps or overlaps"
            )

        current_width = current.end_timestamp_ns - current.start_timestamp_ns

        if current_width != interval_width:
            raise InvalidMetricInputError("empirical intervals must have equal width")

    prepared_returns: list[float] = []
    prepared_flow: list[float] = []
    prepared_pre_depth: list[float] = []
    prepared_depth_drop: list[float] = []

    for previous, current in pairwise(intervals):
        if previous.thin_side_depth <= 0.0:
            raise InvalidMetricInputError(
                "pre-interval thin-side depth must be positive "
                f"at timestamp {current.start_timestamp_ns}"
            )

        log_return = math.log(current.mid_price / previous.mid_price)

        relative_drop = (
            previous.thin_side_depth - current.thin_side_depth
        ) / previous.thin_side_depth

        prepared_returns.append(log_return)
        prepared_flow.append(current.aggressor_flow)
        prepared_pre_depth.append(previous.thin_side_depth)
        prepared_depth_drop.append(relative_drop)

    data = MarketSignatureInput(
        log_returns=tuple(prepared_returns),
        aggressor_flow=tuple(prepared_flow),
        pre_interval_thin_side_depth=tuple(prepared_pre_depth),
        relative_thin_side_depth_drop=tuple(prepared_depth_drop),
    )

    provenance = MarketSignatureInputProvenance(
        source_kind=MarketSignatureSourceKind.EMPIRICAL,
        source_id=source_id,
        preparation_id=(EMPIRICAL_MARKET_SIGNATURE_PREPARATION_ID),
        observation_count=data.observation_count,
    )

    return PreparedMarketSignatureSample(
        data=data,
        provenance=provenance,
    )
