"""Replicate-level calibration outcomes and dataset evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.calibration.contracts import CalibrationRunSpec
from abmforge_finance.exceptions import CalibrationExecutionError
from abmforge_finance.metrics import (
    MarketPriceBasis,
    decision_sign_concentration,
    maximum_drawdown,
    realized_volatility,
    relative_absolute_fundamental_deviation,
    relative_spreads,
    total_depth,
)
from abmforge_finance.recording import FinanceResearchDataset

_ZERO = Decimal("0")


def _mean_decimal(values: tuple[Decimal | None, ...]) -> Decimal | None:
    defined = tuple(value for value in values if value is not None)
    if not defined:
        return None
    return sum(defined, start=_ZERO) / Decimal(len(defined))


@dataclass(frozen=True, slots=True)
class CalibrationRunResult:
    """Research-relevant outcomes for one scenario/treatment replicate."""

    spec: CalibrationRunSpec
    dataset_schema_version: str
    participant_count: int
    decision_count: int
    cancellation_count: int
    order_count: int
    rejected_order_count: int
    trade_count: int
    trade_volume: Decimal
    mid_realized_volatility: float | None
    last_trade_realized_volatility: float | None
    maximum_drawdown: Decimal | None
    mean_relative_spread: Decimal | None
    mean_total_depth: Decimal | None
    mean_absolute_relative_dislocation: Decimal | None
    mean_decision_sign_concentration: Decimal | None

    @property
    def scenario_fingerprint(self) -> str:
        """Return the seed-independent fingerprint of the parent scenario."""

        return self.spec.scenario.fingerprint

    def metric_items(self) -> tuple[tuple[str, int | float | Decimal | None], ...]:
        """Return a stable statistical-summary projection of replicate outcomes."""

        return (
            ("cancellation_count", self.cancellation_count),
            ("decision_count", self.decision_count),
            ("last_trade_realized_volatility", self.last_trade_realized_volatility),
            ("maximum_drawdown", self.maximum_drawdown),
            (
                "mean_absolute_relative_dislocation",
                self.mean_absolute_relative_dislocation,
            ),
            (
                "mean_decision_sign_concentration",
                self.mean_decision_sign_concentration,
            ),
            ("mean_relative_spread", self.mean_relative_spread),
            ("mean_total_depth", self.mean_total_depth),
            ("mid_realized_volatility", self.mid_realized_volatility),
            ("order_count", self.order_count),
            ("rejected_order_count", self.rejected_order_count),
            ("trade_count", self.trade_count),
            ("trade_volume", self.trade_volume),
        )


def evaluate_calibration_dataset(
    spec: CalibrationRunSpec,
    dataset: FinanceResearchDataset,
) -> CalibrationRunResult:
    """Evaluate one completed dataset without fitting or changing model parameters."""

    if not isinstance(spec, CalibrationRunSpec):
        raise TypeError("spec must be a CalibrationRunSpec")
    if not isinstance(dataset, FinanceResearchDataset):
        raise TypeError("dataset must be a FinanceResearchDataset")
    dataset.validate()

    periods = tuple(sorted(row.period for row in dataset.market_states))
    expected = tuple(range(spec.scenario.periods))
    if periods != expected:
        raise CalibrationExecutionError(
            f"market-state periods {periods!r} do not match expected {expected!r}"
        )

    spreads = relative_spreads(dataset)
    depths = total_depth(dataset)
    dislocation = relative_absolute_fundamental_deviation(
        dataset,
        basis=MarketPriceBasis.MID,
    )
    synchronization = decision_sign_concentration(dataset)

    return CalibrationRunResult(
        spec=spec,
        dataset_schema_version=dataset.schema_version,
        participant_count=len(dataset.participants),
        decision_count=len(dataset.decisions),
        cancellation_count=len(dataset.cancellations),
        order_count=len(dataset.orders),
        rejected_order_count=sum(not row.accepted for row in dataset.orders),
        trade_count=len(dataset.trades),
        trade_volume=sum((row.quantity for row in dataset.trades), start=_ZERO),
        mid_realized_volatility=realized_volatility(
            dataset,
            basis=MarketPriceBasis.MID,
        ),
        last_trade_realized_volatility=realized_volatility(
            dataset,
            basis=MarketPriceBasis.LAST_TRADE,
        ),
        maximum_drawdown=maximum_drawdown(
            dataset,
            basis=MarketPriceBasis.MID,
        ),
        mean_relative_spread=_mean_decimal(tuple(point.value for point in spreads)),
        mean_total_depth=_mean_decimal(tuple(point.value for point in depths)),
        mean_absolute_relative_dislocation=_mean_decimal(
            tuple(point.value for point in dislocation)
        ),
        mean_decision_sign_concentration=_mean_decimal(
            tuple(point.value for point in synchronization)
        ),
    )
