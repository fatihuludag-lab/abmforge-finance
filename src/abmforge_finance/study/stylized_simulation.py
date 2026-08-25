"""Simulation-recording adapter for Phase 11 market signatures."""

from __future__ import annotations

from decimal import Decimal

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.metrics import (
    MarketPriceBasis,
    aggressor_executed_flow_imbalance,
    log_returns,
    thin_side_depth,
)
from abmforge_finance.recording import FinanceResearchDataset
from abmforge_finance.study.stylized_pipeline import (
    MarketSignatureInput,
    MarketSignatureInputProvenance,
    MarketSignatureSourceKind,
    PreparedMarketSignatureSample,
)
from abmforge_finance.study.stylized_protocol import (
    stylized_fact_validation_protocol,
)

SIMULATION_MARKET_SIGNATURE_PREPARATION_ID = "phase11-simulation-recording-v1"

_ZERO = Decimal("0")


def _require_simulation_dataset(
    dataset: FinanceResearchDataset,
) -> FinanceResearchDataset:
    if not isinstance(dataset, FinanceResearchDataset):
        raise TypeError("dataset must be a FinanceResearchDataset")

    dataset.validate()
    return dataset


def _validate_analysis_market_states(
    dataset: FinanceResearchDataset,
    *,
    start_period: int,
    stop_period: int,
) -> str:
    required_periods = set(range(start_period - 1, stop_period))

    states_by_period = {
        row.period: row for row in dataset.market_states if row.period in required_periods
    }

    missing = sorted(required_periods.difference(states_by_period))

    if missing:
        raise InvalidMetricInputError(
            f"simulation market states are missing required period {missing[0]}"
        )

    instrument_ids = {row.instrument_id for row in states_by_period.values()}

    if len(instrument_ids) != 1:
        raise InvalidMetricInputError(
            "simulation preparation requires exactly one market-state instrument"
        )

    instrument_id = next(iter(instrument_ids))

    for row in dataset.orders:
        if start_period <= row.period < stop_period and row.instrument_id != instrument_id:
            raise InvalidMetricInputError(
                "simulation analysis-window orders must match the market-state instrument"
            )

    return instrument_id


def prepare_stylized_validation_simulation_sample(
    dataset: FinanceResearchDataset,
    *,
    source_id: str,
) -> PreparedMarketSignatureSample:
    """Prepare one frozen Phase 11 simulation replicate for estimation."""

    dataset = _require_simulation_dataset(dataset)
    protocol = stylized_fact_validation_protocol()

    start_period = protocol.burn_in_periods
    stop_period = protocol.total_periods

    _validate_analysis_market_states(
        dataset,
        start_period=start_period,
        stop_period=stop_period,
    )

    return_points = {
        point.period: point.value
        for point in log_returns(
            dataset,
            basis=MarketPriceBasis.MID,
        )
    }

    flow_points = {
        point.period: point.value for point in aggressor_executed_flow_imbalance(dataset)
    }

    depth_points = {point.period: point.value for point in thin_side_depth(dataset)}

    prepared_returns: list[float] = []
    prepared_flow: list[float] = []
    prepared_pre_depth: list[float] = []
    prepared_depth_drop: list[float] = []

    for period in range(start_period, stop_period):
        return_value = return_points.get(period)

        if return_value is None:
            raise InvalidMetricInputError(
                f"log midpoint return is undefined at analysis period {period}"
            )

        flow_value = flow_points.get(period)

        if flow_value is None:
            raise InvalidMetricInputError(
                f"aggressor-executed-flow-imbalance is undefined at analysis period {period}"
            )

        pre_depth = depth_points.get(period - 1)
        current_depth = depth_points.get(period)

        if pre_depth is None:
            raise InvalidMetricInputError(
                f"pre-interval thin-side depth is undefined at analysis period {period}"
            )

        if current_depth is None:
            raise InvalidMetricInputError(
                f"current thin-side depth is undefined at analysis period {period}"
            )

        if pre_depth <= _ZERO:
            raise InvalidMetricInputError(
                f"pre-interval thin-side depth must be positive at analysis period {period}"
            )

        relative_drop = (pre_depth - current_depth) / pre_depth

        prepared_returns.append(return_value)
        prepared_flow.append(float(flow_value))
        prepared_pre_depth.append(float(pre_depth))
        prepared_depth_drop.append(float(relative_drop))

    data = MarketSignatureInput(
        log_returns=tuple(prepared_returns),
        aggressor_flow=tuple(prepared_flow),
        pre_interval_thin_side_depth=tuple(prepared_pre_depth),
        relative_thin_side_depth_drop=tuple(prepared_depth_drop),
    )

    if data.observation_count != protocol.analysis_horizon:
        raise InvalidMetricInputError(
            "prepared simulation observation count does not match the frozen analysis horizon"
        )

    provenance = MarketSignatureInputProvenance(
        source_kind=MarketSignatureSourceKind.SIMULATION,
        source_id=source_id,
        preparation_id=(SIMULATION_MARKET_SIGNATURE_PREPARATION_ID),
        observation_count=data.observation_count,
    )

    return PreparedMarketSignatureSample(
        data=data,
        provenance=provenance,
    )
