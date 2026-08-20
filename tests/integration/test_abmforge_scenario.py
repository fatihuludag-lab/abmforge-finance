"""End-to-end integration with the released/audited ABMForge Scenario lifecycle."""

from __future__ import annotations

from decimal import Decimal

from abmforge.experiment.scenario import Scenario

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    Exchange,
    Instrument,
    MarketClock,
    Portfolio,
    Side,
    Trader,
    TradingDecision,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents


class BuyerPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del agent_id
        if observation.step == 0:
            return TradingDecision.limit(Side.BUY, Decimal("1"), Decimal("100"))
        return TradingDecision.hold()


class SellerPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del agent_id
        if observation.step == 1:
            return TradingDecision.market(Side.SELL, Decimal("1"))
        return TradingDecision.hold()


class ThreePeriodMarket(FinanceABMModel):
    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        exchange.register(Account("buyer", Decimal("1000")), Portfolio("buyer"))
        exchange.register(
            Account("seller", Decimal("0")),
            Portfolio("seller", (("ACME", Decimal("1")),)),
        )
        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=(Trader("seller", SellerPolicy()), Trader("buyer", BuyerPolicy())),
        )


def test_scenario_drives_finance_clock_exchange_and_recorder() -> None:
    result = Scenario(model=ThreePeriodMarket, seed=42, steps=3, name="three-period").run()
    model = result.model
    assert isinstance(model, ThreePeriodMarket)
    assert model.steps == 3
    assert model.finance.clock.current_step == 3
    assert model.last_finance_step is not None
    assert model.last_finance_step.period == 2
    assert model.last_finance_step.trade_count == 0
    assert model.last_finance_step.last_trade_price == Decimal("100")
    assert model.last_finance_step.price_change == Decimal("0")
    assert model.finance.exchange.account("buyer").cash == Decimal("900")
    assert model.finance.exchange.portfolio("buyer").quantity("ACME") == Decimal("1")
    assert model.finance.exchange.account("seller").cash == Decimal("100")
    assert model.finance.exchange.portfolio("seller").quantity("ACME") == Decimal("0")

    trade_count_records = [
        row for row in result.dataset.model_records if row["metric"] == "finance_trade_count"
    ]
    assert [row["value"] for row in trade_count_records] == [0, 1, 0]
    assert [row["step"] for row in trade_count_records] == [1, 2, 3]
    result.dataset.validate()
