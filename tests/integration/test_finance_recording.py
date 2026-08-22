"""End-to-end ABMForge adapter integration with the finance research recorder."""

from decimal import Decimal

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    Exchange,
    Instrument,
    MarketClock,
    Order,
    OrderType,
    Portfolio,
    Side,
    TimeInForce,
    Trader,
    TradingDecision,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.recording import FinanceResearchRecorder


class BuyMarketPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.market(Side.BUY, Decimal("1"))


class HoldPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.hold()


class RecordedMarket(FinanceABMModel):
    research = FinanceResearchRecorder()

    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        exchange.register(Account("buyer", Decimal("1000")), Portfolio("buyer"))
        exchange.register(
            Account("seller", Decimal("1000")),
            Portfolio("seller", (("ACME", Decimal("2")),)),
        )
        exchange.submit(
            Order(
                order_id="seed-ask",
                agent_id="seller",
                instrument_id="ACME",
                side=Side.SELL,
                order_type=OrderType.LIMIT,
                quantity=Decimal("1"),
                remaining_quantity=Decimal("1"),
                price=Decimal("100"),
                submitted_at=0,
                sequence_number=0,
                time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
            )
        )
        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=(
                Trader("seller", HoldPolicy()),
                Trader("buyer", BuyMarketPolicy()),
            ),
            research_recorder=self.research,
        )


def test_adapter_records_decisions_order_trade_market_and_balances() -> None:
    model = RecordedMarket(seed=42)
    model.research = FinanceResearchRecorder()
    model.setup()
    model.run_for(1)

    dataset = model.research.dataset
    dataset.validate()

    assert dataset.row_counts == {
        "participants": 2,
        "decisions": 2,
        "cancellations": 0,
        "orders": 1,
        "trades": 1,
        "market_states": 1,
        "accounts": 4,
        "positions": 4,
    }
    assert tuple(row.agent_id for row in dataset.decisions) == ("buyer", "seller")
    assert dataset.decisions[1].kind == "hold"
    assert dataset.orders[0].order_id == "finance-order-000000000001"
    assert dataset.orders[0].accepted is True
    assert dataset.trades[0].price == Decimal("100")
    assert dataset.market_states[0].last_trade_price == Decimal("100")

    buyer_post = next(
        row for row in dataset.accounts if row.agent_id == "buyer" and row.phase == "post"
    )
    seller_post = next(
        row for row in dataset.positions if row.agent_id == "seller" and row.phase == "post"
    )
    assert buyer_post.cash == Decimal("900")
    assert seller_post.quantity == Decimal("1")
