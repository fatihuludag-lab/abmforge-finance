"""Tests for Phase 11 simulation-recording preparation."""

from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal

import pytest

import abmforge_finance.study.stylized_simulation as stylized_simulation_module
from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.metrics import (
    MetricPoint,
)
from abmforge_finance.metrics import (
    thin_side_depth as market_thin_side_depth,
)
from abmforge_finance.recording import (
    FinanceResearchDataset,
    MarketStateRecord,
    OrderRecord,
)
from abmforge_finance.study.stylized_pipeline import (
    MarketSignatureSourceKind,
    estimate_prepared_market_signatures,
)
from abmforge_finance.study.stylized_protocol import (
    stylized_fact_validation_protocol,
)
from abmforge_finance.study.stylized_simulation import (
    SIMULATION_MARKET_SIGNATURE_PREPARATION_ID,
    prepare_stylized_validation_simulation_sample,
)

_INSTRUMENT = "SIM"
_ONE = Decimal("1")
_ZERO = Decimal("0")


def _market_state(period: int) -> MarketStateRecord:
    mid = Decimal(10_000 + period)
    bid_depth = Decimal(10 + period % 7)
    ask_depth = Decimal(12 + period % 5)

    return MarketStateRecord(
        period=period,
        instrument_id=_INSTRUMENT,
        fundamental_value=mid,
        best_bid=mid - _ONE,
        best_ask=mid + _ONE,
        mid_price=mid,
        spread=Decimal("2"),
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        imbalance=None,
        order_count=1,
        last_trade_price=mid,
        price_change=None if period == 0 else _ONE,
        fee_balance=_ZERO,
    )


def _aggressor_order(period: int) -> OrderRecord:
    return OrderRecord(
        period=period,
        order_id=f"order-{period}",
        sequence_number=period,
        agent_id="agent",
        instrument_id=_INSTRUMENT,
        side="buy" if period % 2 == 0 else "sell",
        order_type="market",
        quantity=_ONE,
        limit_price=None,
        submitted_at=period,
        time_in_force="ioc",
        accepted=True,
        executed_quantity=_ONE,
        remaining_quantity=_ZERO,
        cancelled_quantity=_ZERO,
        rested=False,
        rejection_type=None,
        rejection_message=None,
    )


@pytest.fixture(scope="module")
def simulation_dataset() -> FinanceResearchDataset:
    protocol = stylized_fact_validation_protocol()

    dataset = FinanceResearchDataset(
        market_states=tuple(_market_state(period) for period in range(protocol.total_periods)),
        orders=tuple(
            _aggressor_order(period)
            for period in range(
                protocol.burn_in_periods,
                protocol.total_periods,
            )
        ),
    )

    dataset.validate()
    return dataset


def test_simulation_adapter_produces_frozen_analysis_horizon(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()

    sample = prepare_stylized_validation_simulation_sample(
        simulation_dataset,
        source_id="replicate-000",
    )

    assert sample.data.observation_count == protocol.analysis_horizon == 4096
    assert sample.provenance.source_kind is MarketSignatureSourceKind.SIMULATION
    assert sample.provenance.source_id == "replicate-000"
    assert sample.provenance.preparation_id == (SIMULATION_MARKET_SIGNATURE_PREPARATION_ID)


def test_simulation_adapter_uses_first_post_burn_in_interval(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()

    sample = prepare_stylized_validation_simulation_sample(
        simulation_dataset,
        source_id="replicate-000",
    )

    first_period = protocol.burn_in_periods

    previous_state = _market_state(first_period - 1)
    current_state = _market_state(first_period)

    assert previous_state.mid_price is not None

    assert current_state.mid_price is not None

    expected_return = math.log(float(current_state.mid_price / previous_state.mid_price))

    expected_pre_depth = min(
        previous_state.bid_depth,
        previous_state.ask_depth,
    )

    expected_current_depth = min(
        current_state.bid_depth,
        current_state.ask_depth,
    )

    expected_drop = (expected_pre_depth - expected_current_depth) / expected_pre_depth

    assert sample.data.log_returns[0] == pytest.approx(expected_return)
    assert sample.data.pre_interval_thin_side_depth[0] == pytest.approx(float(expected_pre_depth))
    assert sample.data.relative_thin_side_depth_drop[0] == pytest.approx(float(expected_drop))

    expected_flow = 1.0 if first_period % 2 == 0 else -1.0
    assert sample.data.aggressor_flow[0] == expected_flow


def test_simulation_adapter_rejects_missing_required_market_state(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()
    missing_period = protocol.burn_in_periods + 10

    dataset = replace(
        simulation_dataset,
        market_states=tuple(
            row for row in simulation_dataset.market_states if row.period != missing_period
        ),
    )

    with pytest.raises(
        InvalidMetricInputError,
        match=f"missing required period {missing_period}",
    ):
        prepare_stylized_validation_simulation_sample(
            dataset,
            source_id="replicate-missing-state",
        )


def test_simulation_adapter_rejects_undefined_aggressor_flow(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()
    missing_period = protocol.burn_in_periods

    dataset = replace(
        simulation_dataset,
        orders=tuple(row for row in simulation_dataset.orders if row.period != missing_period),
    )

    with pytest.raises(
        InvalidMetricInputError,
        match=("aggressor-executed-flow-imbalance is undefined"),
    ):
        prepare_stylized_validation_simulation_sample(
            dataset,
            source_id="replicate-no-flow",
        )


def test_simulation_adapter_does_not_coerce_no_flow_to_zero(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()
    target = protocol.burn_in_periods + 3

    dataset = replace(
        simulation_dataset,
        orders=tuple(row for row in simulation_dataset.orders if row.period != target),
    )

    with pytest.raises(
        InvalidMetricInputError,
        match=f"undefined at analysis period {target}",
    ):
        prepare_stylized_validation_simulation_sample(
            dataset,
            source_id="replicate-no-zero-imputation",
        )


def test_simulation_adapter_rejects_zero_pre_interval_depth(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()
    pre_period = protocol.burn_in_periods - 1

    states = list(simulation_dataset.market_states)

    states[pre_period] = replace(
        states[pre_period],
        bid_depth=_ZERO,
    )

    dataset = replace(
        simulation_dataset,
        market_states=tuple(states),
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="pre-interval thin-side depth must be positive",
    ):
        prepare_stylized_validation_simulation_sample(
            dataset,
            source_id="replicate-zero-depth",
        )


def test_simulation_adapter_rejects_cross_instrument_order(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    orders = list(simulation_dataset.orders)

    orders[0] = replace(
        orders[0],
        instrument_id="OTHER",
    )

    dataset = replace(
        simulation_dataset,
        orders=tuple(orders),
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="orders must match the market-state instrument",
    ):
        prepare_stylized_validation_simulation_sample(
            dataset,
            source_id="replicate-cross-instrument",
        )


def test_simulation_adapter_requires_finance_dataset() -> None:
    with pytest.raises(
        TypeError,
        match="FinanceResearchDataset",
    ):
        prepare_stylized_validation_simulation_sample(
            object(),  # type: ignore[arg-type]
            source_id="invalid",
        )


def test_simulation_sample_runs_through_shared_signature_pipeline(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()

    sample = prepare_stylized_validation_simulation_sample(
        simulation_dataset,
        source_id="replicate-e2e",
    )

    estimates = estimate_prepared_market_signatures(sample)

    assert estimates.sf01_return_linear_dependence.observation_count == protocol.analysis_horizon
    assert estimates.sf02_return_tail_shape.observation_count == protocol.analysis_horizon
    assert estimates.sf03_volatility_clustering.observation_count == protocol.analysis_horizon
    assert estimates.sf04_aggressor_flow_price_impact.observation_count == protocol.analysis_horizon
    assert estimates.sf06_liquidity_fragility.observation_count == protocol.analysis_horizon
    assert (
        estimates.sf07_aggressor_sign_persistence.nonzero_observation_count
        == protocol.analysis_horizon
    )

    assert estimates.sf05_depth_conditioned_price_impact.low_depth.observation_count > 1
    assert estimates.sf05_depth_conditioned_price_impact.high_depth.observation_count > 1

    assert math.isfinite(estimates.sf04_aggressor_flow_price_impact.slope)
    assert math.isfinite(
        estimates.sf05_depth_conditioned_price_impact.low_minus_high_absolute_slope
    )
    assert math.isfinite(estimates.sf06_liquidity_fragility.depletion_spearman)
    assert math.isfinite(estimates.sf06_liquidity_fragility.pre_depth_spearman)


def test_simulation_preparation_and_estimation_are_deterministic(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    first_sample = prepare_stylized_validation_simulation_sample(
        simulation_dataset,
        source_id="replicate-deterministic",
    )
    second_sample = prepare_stylized_validation_simulation_sample(
        simulation_dataset,
        source_id="replicate-deterministic",
    )

    assert first_sample == second_sample

    first_estimates = estimate_prepared_market_signatures(first_sample)
    second_estimates = estimate_prepared_market_signatures(second_sample)

    assert first_estimates == second_estimates


def test_simulation_adapter_rejects_multiple_market_state_instruments(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()
    target = protocol.burn_in_periods + 5

    states = list(simulation_dataset.market_states)
    states[target] = replace(
        states[target],
        instrument_id="OTHER",
    )

    dataset = replace(
        simulation_dataset,
        market_states=tuple(states),
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="exactly one market-state instrument",
    ):
        prepare_stylized_validation_simulation_sample(
            dataset,
            source_id="multiple-instruments",
        )


def test_simulation_adapter_rejects_undefined_midpoint_return(
    simulation_dataset: FinanceResearchDataset,
) -> None:
    protocol = stylized_fact_validation_protocol()
    target = protocol.burn_in_periods

    states = list(simulation_dataset.market_states)
    states[target] = replace(
        states[target],
        mid_price=None,
    )

    dataset = replace(
        simulation_dataset,
        market_states=tuple(states),
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="log midpoint return is undefined",
    ):
        prepare_stylized_validation_simulation_sample(
            dataset,
            source_id="undefined-midpoint",
        )


def test_simulation_adapter_rejects_missing_pre_depth_metric_point(
    simulation_dataset: FinanceResearchDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = stylized_fact_validation_protocol()
    missing_period = protocol.burn_in_periods - 1

    original = market_thin_side_depth

    def incomplete_depth(
        dataset: FinanceResearchDataset,
    ) -> tuple[MetricPoint[Decimal], ...]:
        return tuple(point for point in original(dataset) if point.period != missing_period)

    monkeypatch.setattr(
        stylized_simulation_module,
        "thin_side_depth",
        incomplete_depth,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="pre-interval thin-side depth is undefined",
    ):
        prepare_stylized_validation_simulation_sample(
            simulation_dataset,
            source_id="missing-pre-depth-point",
        )


def test_simulation_adapter_rejects_missing_current_depth_metric_point(
    simulation_dataset: FinanceResearchDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = stylized_fact_validation_protocol()
    missing_period = protocol.burn_in_periods

    original = market_thin_side_depth

    def incomplete_depth(
        dataset: FinanceResearchDataset,
    ) -> tuple[MetricPoint[Decimal], ...]:
        return tuple(point for point in original(dataset) if point.period != missing_period)

    monkeypatch.setattr(
        stylized_simulation_module,
        "thin_side_depth",
        incomplete_depth,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="current thin-side depth is undefined",
    ):
        prepare_stylized_validation_simulation_sample(
            simulation_dataset,
            source_id="missing-current-depth-point",
        )


def test_simulation_adapter_rejects_protocol_horizon_mismatch(
    simulation_dataset: FinanceResearchDataset,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = stylized_fact_validation_protocol()

    class ProtocolStub:
        burn_in_periods = protocol.burn_in_periods
        total_periods = protocol.total_periods
        analysis_horizon = protocol.analysis_horizon + 1

    monkeypatch.setattr(
        stylized_simulation_module,
        "stylized_fact_validation_protocol",
        ProtocolStub,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="does not match the frozen analysis horizon",
    ):
        prepare_stylized_validation_simulation_sample(
            simulation_dataset,
            source_id="horizon-mismatch",
        )
