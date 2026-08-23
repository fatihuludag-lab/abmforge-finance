"""Controlled downstream market effects of narrative synchronization."""

from decimal import Decimal

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    DynamicPassiveLiquidityPolicy,
    Exchange,
    Instrument,
    MarketClock,
    NarrativeDirection,
    NarrativeHomogeneityTreatment,
    Portfolio,
    Side,
    Trader,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.experiments import (
    NarrativeDirectionSchedule,
    evaluate_narrative_market_stability,
    evaluate_narrative_market_stability_sweep,
)
from abmforge_finance.recording import FinanceResearchDataset, FinanceResearchRecorder

_PERIODS = 4
_LEVELS = 5
_LEVEL_QUANTITY = Decimal("2")
_REFERENCE_SIDE_DEPTH = Decimal("10")
_REFERENCE_SPREAD = Decimal("2")


def _agent_ids() -> tuple[str, ...]:
    return tuple(f"narrative-{index:04d}" for index in range(8))


def _treatment(homogeneity: Decimal) -> NarrativeHomogeneityTreatment:
    return NarrativeHomogeneityTreatment(
        f"H={homogeneity}",
        _agent_ids(),
        homogeneity,
        NarrativeDirection.BULLISH,
        active_from=0,
        active_until=_PERIODS,
    )


_SCHEDULE = NarrativeDirectionSchedule(
    (
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
    )
)


class NarrativeStabilityMarket(FinanceABMModel):
    def __init__(self, treatment: NarrativeHomogeneityTreatment) -> None:
        self._treatment = treatment
        super().__init__(seed=42)

    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        traders: list[Trader] = []

        for offset in range(1, _LEVELS + 1):
            bid_id = f"00-bid-{offset:02d}"
            ask_id = f"01-ask-{offset:02d}"
            exchange.register(
                Account(bid_id, Decimal("100000")),
                Portfolio(bid_id),
            )
            exchange.register(
                Account(ask_id, Decimal("0")),
                Portfolio(ask_id, (("ACME", Decimal("100")),)),
            )
            traders.extend(
                (
                    Trader(
                        bid_id,
                        DynamicPassiveLiquidityPolicy(
                            Side.BUY,
                            _LEVEL_QUANTITY,
                            instrument.tick_size,
                            offset_ticks=offset,
                        ),
                    ),
                    Trader(
                        ask_id,
                        DynamicPassiveLiquidityPolicy(
                            Side.SELL,
                            _LEVEL_QUANTITY,
                            instrument.tick_size,
                            offset_ticks=offset,
                        ),
                    ),
                )
            )

        narrative_policy = _SCHEDULE.policy_for(
            self._treatment,
            quantity=Decimal("1"),
        )
        for agent_id in self._treatment.agent_ids:
            exchange.register(
                Account(agent_id, Decimal("100000")),
                Portfolio(agent_id, (("ACME", Decimal("100")),)),
            )
            traders.append(Trader(agent_id, narrative_policy))

        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=tuple(traders),
            research_recorder=FinanceResearchRecorder(),
        )


def _dataset(homogeneity: Decimal) -> FinanceResearchDataset:
    treatment = _treatment(homogeneity)
    model = NarrativeStabilityMarket(treatment)
    model.setup()
    model.run_for(_PERIODS)
    recorder = model.finance.research_recorder
    assert recorder is not None
    return recorder.dataset


def test_balanced_and_homogeneous_flow_diverge_on_thin_side_stress() -> None:
    balanced_treatment = _treatment(Decimal("0"))
    homogeneous_treatment = _treatment(Decimal("1"))

    balanced = evaluate_narrative_market_stability(
        _dataset(Decimal("0")),
        balanced_treatment,
        reference_side_depth=_REFERENCE_SIDE_DEPTH,
        reference_spread=_REFERENCE_SPREAD,
    )
    homogeneous = evaluate_narrative_market_stability(
        _dataset(Decimal("1")),
        homogeneous_treatment,
        reference_side_depth=_REFERENCE_SIDE_DEPTH,
        reference_spread=_REFERENCE_SPREAD,
    )

    assert balanced.mean_decision_concentration == Decimal("0")
    assert homogeneous.mean_decision_concentration == Decimal("1")
    assert balanced.mean_accepted_order_concentration == Decimal("0")
    assert homogeneous.mean_accepted_order_concentration == Decimal("1")
    assert balanced.mean_executed_flow_concentration == Decimal("0")
    assert homogeneous.mean_executed_flow_concentration == Decimal("1")

    assert balanced.mean_total_depth == homogeneous.mean_total_depth == Decimal("12")
    assert (
        balanced.mean_total_depth_depletion
        == homogeneous.mean_total_depth_depletion
        == Decimal("0.4")
    )

    assert balanced.mean_thin_side_depth == Decimal("6")
    assert homogeneous.mean_thin_side_depth == Decimal("2")
    assert balanced.mean_thin_side_depletion == Decimal("0.4")
    assert homogeneous.mean_thin_side_depletion == Decimal("0.8")
    assert balanced.mean_depth_asymmetry == Decimal("0")
    assert homogeneous.mean_depth_asymmetry is not None
    expected_asymmetry = Decimal("2") / Decimal("3")
    assert abs(homogeneous.mean_depth_asymmetry - expected_asymmetry) <= Decimal("1e-27")

    assert balanced.mean_absolute_relative_dislocation == Decimal("0")
    assert homogeneous.mean_absolute_relative_dislocation == Decimal("0.02")
    assert balanced.mid_realized_volatility == 0.0
    assert homogeneous.mid_realized_volatility is not None
    assert homogeneous.mid_realized_volatility > 0.0
    assert balanced.maximum_drawdown == Decimal("0")
    assert homogeneous.maximum_drawdown is not None
    assert homogeneous.maximum_drawdown < Decimal("0")

    assert balanced.treatment_rejected_order_count == 0
    assert homogeneous.treatment_rejected_order_count == 0
    assert (
        balanced.treatment_executed_volume == homogeneous.treatment_executed_volume == Decimal("32")
    )
    assert balanced.market_trade_volume == homogeneous.market_trade_volume == Decimal("32")


def test_controlled_homogeneity_sweep_has_exact_thin_side_and_dislocation_gradient() -> None:
    homogeneities = (
        Decimal("0"),
        Decimal("0.25"),
        Decimal("0.50"),
        Decimal("0.75"),
        Decimal("1"),
    )
    treatments = tuple(_treatment(value) for value in homogeneities)
    datasets = tuple(_dataset(value) for value in homogeneities)

    outcomes = evaluate_narrative_market_stability_sweep(
        datasets,
        treatments,
        reference_side_depth=_REFERENCE_SIDE_DEPTH,
        reference_spread=_REFERENCE_SPREAD,
    )

    assert tuple(item.assigned_homogeneity for item in outcomes) == homogeneities
    assert tuple(item.mean_decision_concentration for item in outcomes) == homogeneities
    assert tuple(item.mean_accepted_order_concentration for item in outcomes) == homogeneities
    assert tuple(item.mean_executed_flow_concentration for item in outcomes) == homogeneities
    assert tuple(item.mean_thin_side_depletion for item in outcomes) == (
        Decimal("0.4"),
        Decimal("0.5"),
        Decimal("0.6"),
        Decimal("0.7"),
        Decimal("0.8"),
    )
    assert tuple(item.mean_absolute_relative_dislocation for item in outcomes) == (
        Decimal("0"),
        Decimal("0.005"),
        Decimal("0.01"),
        Decimal("0.015"),
        Decimal("0.02"),
    )
    assert all(item.treatment_rejected_order_count == 0 for item in outcomes)
    assert all(item.treatment_executed_volume == Decimal("32") for item in outcomes)


def test_stability_outcome_metric_projection_is_stable() -> None:
    treatment = _treatment(Decimal("0.5"))
    outcome = evaluate_narrative_market_stability(
        _dataset(Decimal("0.5")),
        treatment,
        reference_side_depth=_REFERENCE_SIDE_DEPTH,
        reference_spread=_REFERENCE_SPREAD,
    )

    names = tuple(name for name, _ in outcome.metric_items())
    assert names == tuple(sorted(names))
    assert dict(outcome.metric_items())["mean_thin_side_depletion"] == Decimal("0.6")
