"""Integration test for a controlled two-sided passive-liquidity baseline."""

from decimal import Decimal

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    Exchange,
    Instrument,
    MarketClock,
    PassiveLiquidityPolicy,
    Portfolio,
    Side,
    Trader,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.metrics import relative_spreads, total_depth
from abmforge_finance.recording import FinanceResearchRecorder


class PassiveBaselineMarket(FinanceABMModel):
    research = FinanceResearchRecorder()

    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        exchange.register(Account("lp-bid", Decimal("10000")), Portfolio("lp-bid"))
        exchange.register(
            Account("lp-ask", Decimal("0")),
            Portfolio("lp-ask", (("ACME", Decimal("20")),)),
        )

        traders = (
            Trader(
                "lp-bid",
                PassiveLiquidityPolicy(
                    Side.BUY,
                    Decimal("10"),
                    instrument.tick_size,
                ),
            ),
            Trader(
                "lp-ask",
                PassiveLiquidityPolicy(
                    Side.SELL,
                    Decimal("10"),
                    instrument.tick_size,
                ),
            ),
        )
        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=traders,
            research_recorder=self.research,
        )


def test_two_sided_static_liquidity_is_seeded_once_and_remains_recorded() -> None:
    model = PassiveBaselineMarket(seed=42)
    model.research = FinanceResearchRecorder()
    model.setup()
    model.run_for(2)

    snapshot = model.finance.exchange.snapshot()
    assert snapshot.best_bid == Decimal("99")
    assert snapshot.best_ask == Decimal("101")
    assert snapshot.order_count == 2
    assert model.last_finance_step is not None
    assert model.last_finance_step.trade_count == 0
    assert model.last_finance_step.hold_count == 2

    dataset = model.research.dataset
    dataset.validate()
    assert dataset.row_counts["decisions"] == 4
    assert dataset.row_counts["orders"] == 2
    assert dataset.row_counts["trades"] == 0
    assert dataset.row_counts["market_states"] == 2

    spreads = relative_spreads(dataset)
    assert tuple(point.period for point in spreads) == (0, 1)
    assert tuple(point.value for point in spreads) == (
        Decimal("0.02"),
        Decimal("0.02"),
    )
    assert tuple(point.value for point in total_depth(dataset)) == (
        Decimal("20"),
        Decimal("20"),
    )
