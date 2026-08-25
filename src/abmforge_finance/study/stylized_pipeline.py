"""Canonical source-neutral pipeline for Phase 11 market signatures."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.stylized_estimators import (
    MarketSignatureEstimates,
    estimate_market_signatures,
)
from abmforge_finance.study.stylized_protocol import (
    stylized_fact_validation_protocol,
)


class MarketSignatureSourceKind(str, Enum):
    """Origin of one prepared market-signature sample."""

    SIMULATION = "simulation"
    EMPIRICAL = "empirical"


def _non_empty_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidMetricInputError(f"{label} must be a non-empty string")
    return value.strip()


def _finite_tuple(
    values: object,
    *,
    label: str,
) -> tuple[float, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} must be a tuple")

    if len(values) < 2:
        raise InvalidMetricInputError(f"{label} must contain at least two observations")

    output: list[float] = []

    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidMetricInputError(f"{label}[{index}] must be a finite real number")

        number = float(value)

        if not math.isfinite(number):
            raise InvalidMetricInputError(f"{label}[{index}] must be a finite real number")

        output.append(number)

    return tuple(output)


@dataclass(frozen=True, slots=True)
class MarketSignatureInput:
    """Aligned numeric series consumed by the shared estimators."""

    log_returns: tuple[float, ...]
    aggressor_flow: tuple[float, ...]
    pre_interval_thin_side_depth: tuple[float, ...]
    relative_thin_side_depth_drop: tuple[float, ...]

    def __post_init__(self) -> None:
        log_returns = _finite_tuple(
            self.log_returns,
            label="log_returns",
        )
        aggressor_flow = _finite_tuple(
            self.aggressor_flow,
            label="aggressor_flow",
        )
        pre_depth = _finite_tuple(
            self.pre_interval_thin_side_depth,
            label="pre_interval_thin_side_depth",
        )
        depth_drop = _finite_tuple(
            self.relative_thin_side_depth_drop,
            label="relative_thin_side_depth_drop",
        )

        lengths = {
            len(log_returns),
            len(aggressor_flow),
            len(pre_depth),
            len(depth_drop),
        }

        if len(lengths) != 1:
            raise InvalidMetricInputError(
                "all market-signature input series must have the same length"
            )

        if any(value < 0.0 for value in pre_depth):
            raise InvalidMetricInputError("pre_interval_thin_side_depth must be non-negative")

        object.__setattr__(self, "log_returns", log_returns)
        object.__setattr__(self, "aggressor_flow", aggressor_flow)
        object.__setattr__(
            self,
            "pre_interval_thin_side_depth",
            pre_depth,
        )
        object.__setattr__(
            self,
            "relative_thin_side_depth_drop",
            depth_drop,
        )

    @property
    def observation_count(self) -> int:
        """Return the aligned observation count."""

        return len(self.log_returns)


@dataclass(frozen=True, slots=True)
class MarketSignatureInputProvenance:
    """Source and preparation identity for one canonical input sample."""

    source_kind: MarketSignatureSourceKind
    source_id: str
    preparation_id: str
    observation_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, MarketSignatureSourceKind):
            raise TypeError("source_kind must be a MarketSignatureSourceKind")

        object.__setattr__(
            self,
            "source_id",
            _non_empty_text(self.source_id, label="source_id"),
        )
        object.__setattr__(
            self,
            "preparation_id",
            _non_empty_text(
                self.preparation_id,
                label="preparation_id",
            ),
        )

        if (
            isinstance(self.observation_count, bool)
            or not isinstance(self.observation_count, int)
            or self.observation_count < 1
        ):
            raise InvalidMetricInputError("observation_count must be a positive integer")


@dataclass(frozen=True, slots=True)
class PreparedMarketSignatureSample:
    """Canonical market-signature input paired with provenance."""

    data: MarketSignatureInput
    provenance: MarketSignatureInputProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.data, MarketSignatureInput):
            raise TypeError("data must be a MarketSignatureInput")

        if not isinstance(
            self.provenance,
            MarketSignatureInputProvenance,
        ):
            raise TypeError("provenance must be a MarketSignatureInputProvenance")

        if self.provenance.observation_count != self.data.observation_count:
            raise InvalidMetricInputError("provenance observation_count must match prepared data")


def estimate_prepared_market_signatures(
    sample: PreparedMarketSignatureSample,
) -> MarketSignatureEstimates:
    """Estimate the frozen Phase 11 signatures from canonical prepared data."""

    if not isinstance(sample, PreparedMarketSignatureSample):
        raise TypeError("sample must be a PreparedMarketSignatureSample")

    protocol = stylized_fact_validation_protocol()

    fact_parameters = {fact.fact_id: dict(fact.parameters) for fact in protocol.facts}

    sf02 = fact_parameters["SF-02"]
    sf05 = fact_parameters["SF-05"]

    return estimate_market_signatures(
        log_returns=sample.data.log_returns,
        aggressor_flow=sample.data.aggressor_flow,
        pre_interval_thin_side_depth=(sample.data.pre_interval_thin_side_depth),
        relative_thin_side_depth_drop=(sample.data.relative_thin_side_depth_drop),
        maximum_lag=protocol.maximum_acf_lag,
        tail_threshold_sigma=float(sf02["tail_threshold_sigma"]),
        low_depth_quantile=float(sf05["low_depth_quantile"]),
        high_depth_quantile=float(sf05["high_depth_quantile"]),
    )
