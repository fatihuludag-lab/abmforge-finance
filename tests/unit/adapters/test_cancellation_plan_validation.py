"""Adapter validation tests for cancellation-plan safety."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    Account,
    CancelIntent,
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
    TradingPlan,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.exceptions import InvalidTradingPlanError


class ForeignCancelPolicy:
    def plan(self, observation, *, agent_id, active_order_ids):  # type: ignore[no-untyped-def]
        del observation, agent_id, active_order_ids
        return TradingPlan(
            (CancelIntent("victim-order"),),
            TradingDecision.hold(),
        )


class HoldPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.hold()


class InvalidCancellationMarket(FinanceABMModel):
    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        exchange.register(
            Account("attacker", Decimal("1000")),
            Portfolio("attacker"),
        )
        exchange.register(
            Account("victim", Decimal("0")),
            Portfolio("victim", (("ACME", Decimal("2")),)),
        )
        exchange.submit(
            Order(
                "victim-order",
                "victim",
                "ACME",
                Side.SELL,
                OrderType.LIMIT,
                Decimal("1"),
                Decimal("1"),
                Decimal("101"),
                0,
                0,
                TimeInForce.GOOD_TIL_CANCELLED,
            )
        )
        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=(
                Trader("attacker", ForeignCancelPolicy()),
                Trader("victim", HoldPolicy()),
            ),
        )


def test_all_cancellations_are_validated_before_exchange_mutation() -> None:
    model = InvalidCancellationMarket(seed=42)
    model.setup()

    with pytest.raises(InvalidTradingPlanError, match="cannot cancel"):
        model.run_for(1)

    assert model.finance.exchange.order("victim-order") is not None
    assert model.finance.exchange.snapshot().order_count == 1
