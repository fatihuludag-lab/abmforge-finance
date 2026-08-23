"""End-to-end integration of deterministic narrative policy with the market stack."""

from decimal import Decimal

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    Exchange,
    Instrument,
    MarketClock,
    NarrativeDirection,
    NarrativeExposure,
    NarrativePolicy,
    NarrativeState,
    PassiveLiquidityPolicy,
    Portfolio,
    Side,
    Trader,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.recording import FinanceResearchRecorder


class NarrativeMarket(FinanceABMModel):
    recorder = FinanceResearchRecorder()

    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        exchange.register(
            Account("a-ask", Decimal("0")),
            Portfolio("a-ask", (("ACME", Decimal("10")),)),
        )
        exchange.register(
            Account("b-narrative", Decimal("1000")),
            Portfolio("b-narrative"),
        )

        narrative_policy = NarrativePolicy(
            Decimal("1"),
            narratives=(
                NarrativeState(
                    "growth",
                    NarrativeDirection.BULLISH,
                    Decimal("1"),
                    Decimal("1"),
                    0,
                    1,
                ),
            ),
            exposures=(
                NarrativeExposure(
                    "b-narrative",
                    "growth",
                    Decimal("1"),
                ),
            ),
        )

        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=(
                Trader(
                    "a-ask",
                    PassiveLiquidityPolicy(
                        Side.SELL,
                        Decimal("2"),
                        instrument.tick_size,
                    ),
                ),
                Trader("b-narrative", narrative_policy),
            ),
            research_recorder=self.recorder,
        )


def test_narrative_decision_flows_through_existing_exchange_and_recorder() -> None:
    model = NarrativeMarket(seed=42)
    model.recorder = FinanceResearchRecorder()
    model.setup()
    model.run_for(1)

    assert model.last_finance_step is not None
    assert model.last_finance_step.trade_count == 1

    exchange = model.finance.exchange
    assert exchange.account("b-narrative").cash == Decimal("899")
    assert exchange.portfolio("b-narrative").quantity("ACME") == Decimal("1")
    assert exchange.account("a-ask").cash == Decimal("101")
    assert exchange.portfolio("a-ask").quantity("ACME") == Decimal("9")

    snapshot = exchange.snapshot()
    assert snapshot.best_ask == Decimal("101")
    assert snapshot.order_count == 1

    dataset = model.recorder.dataset
    dataset.validate()
    assert dataset.row_counts["decisions"] == 2
    assert dataset.row_counts["orders"] == 2
    assert dataset.row_counts["trades"] == 1
    assert dataset.row_counts["market_states"] == 1
