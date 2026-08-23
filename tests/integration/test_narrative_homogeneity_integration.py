"""Controlled mechanism tests for assigned narrative homogeneity."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    Exchange,
    Instrument,
    MarketClock,
    NarrativeDirection,
    PassiveLiquidityPolicy,
    Portfolio,
    Side,
    Trader,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.experiments import (
    NarrativeHomogeneityTreatment,
    measure_narrative_homogeneity,
)
from abmforge_finance.recording import FinanceResearchRecorder


def _agent_ids() -> tuple[str, ...]:
    return tuple(f"narrative-{index:04d}" for index in range(8))


class NarrativeHomogeneityMarket(FinanceABMModel):
    def __init__(self, treatment: NarrativeHomogeneityTreatment) -> None:
        self._treatment = treatment
        super().__init__(seed=42)

    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)

        exchange.register(
            Account("00-lp-bid", Decimal("10000")),
            Portfolio("00-lp-bid"),
        )
        exchange.register(
            Account("01-lp-ask", Decimal("0")),
            Portfolio("01-lp-ask", (("ACME", Decimal("20")),)),
        )

        traders: list[Trader] = [
            Trader(
                "00-lp-bid",
                PassiveLiquidityPolicy(
                    Side.BUY,
                    Decimal("20"),
                    instrument.tick_size,
                ),
            ),
            Trader(
                "01-lp-ask",
                PassiveLiquidityPolicy(
                    Side.SELL,
                    Decimal("20"),
                    instrument.tick_size,
                ),
            ),
        ]

        shared_policy = self._treatment.policy(quantity=Decimal("1"))
        for agent_id in self._treatment.agent_ids:
            exchange.register(
                Account(agent_id, Decimal("1000")),
                Portfolio(agent_id, (("ACME", Decimal("1")),)),
            )
            traders.append(Trader(agent_id, shared_policy))

        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=tuple(traders),
            research_recorder=FinanceResearchRecorder(),
        )


@pytest.mark.parametrize(
    "homogeneity",
    [
        Decimal("0"),
        Decimal("0.25"),
        Decimal("0.50"),
        Decimal("0.75"),
        Decimal("1"),
    ],
)
def test_assigned_homogeneity_equals_realized_decision_and_order_concentration(
    homogeneity: Decimal,
) -> None:
    treatment = NarrativeHomogeneityTreatment(
        f"H={homogeneity}",
        _agent_ids(),
        homogeneity,
        NarrativeDirection.BULLISH,
    )
    model = NarrativeHomogeneityMarket(treatment)
    model.setup()
    model.run_for(1)

    recorder = model.finance.research_recorder
    assert recorder is not None
    measurements = measure_narrative_homogeneity(recorder.dataset, treatment)

    assert len(measurements) == 1
    measurement = measurements[0]
    assert measurement.treatment_active
    assert measurement.assigned_homogeneity == homogeneity
    assert measurement.directional_decision_count == 8
    assert measurement.hold_decisions == 0
    assert measurement.decision_concentration == homogeneity
    assert measurement.accepted_directional_order_count == 8
    assert measurement.rejected_orders == 0
    assert measurement.accepted_order_concentration == homogeneity
    assert model.last_finance_step is not None
    assert model.last_finance_step.trade_count == 8


def test_measurement_excludes_passive_liquidity_provider_decisions() -> None:
    treatment = NarrativeHomogeneityTreatment(
        "balanced",
        _agent_ids(),
        Decimal("0"),
        NarrativeDirection.BULLISH,
    )
    model = NarrativeHomogeneityMarket(treatment)
    model.setup()
    model.run_for(1)

    recorder = model.finance.research_recorder
    assert recorder is not None
    measurement = measure_narrative_homogeneity(
        recorder.dataset,
        treatment,
    )[0]

    assert measurement.buy_decisions == 4
    assert measurement.sell_decisions == 4
    assert measurement.decision_concentration == Decimal("0")
