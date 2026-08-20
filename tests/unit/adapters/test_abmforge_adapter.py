"""Unit tests for deterministic ABMForge finance orchestration."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest

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
from abmforge_finance.exceptions import (
    FinanceAdapterNotInitializedError,
    FinanceClockDriftError,
    FinanceSeedUnavailableError,
    InvalidFinanceComponentsError,
)


class HoldPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.hold()


class InvalidTickThenLimitPolicy:
    def __init__(self, price: Decimal) -> None:
        self.price = price

    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.limit(Side.BUY, Decimal("1"), self.price)


def _components(*, traders: tuple[Trader, ...], clock_step: int = 0) -> FinanceComponents:
    instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
    exchange = Exchange(instrument)
    for trader in traders:
        exchange.register(Account(trader.agent_id, Decimal("1000")), Portfolio(trader.agent_id))
    return FinanceComponents(
        exchange=exchange,
        clock=MarketClock(clock_step),
        fundamental=ConstantFundamentalValue(Decimal("100")),
        traders=traders,
    )


class StaticFinanceModel(FinanceABMModel):
    bundle: FinanceComponents | None = None

    def build_finance_components(self) -> FinanceComponents:
        assert self.bundle is not None
        return self.bundle


def test_finance_state_is_unavailable_before_setup() -> None:
    model = StaticFinanceModel(seed=7)
    with pytest.raises(FinanceAdapterNotInitializedError):
        _ = model.finance


def test_setup_sorts_traders_and_uses_exchange_submission_sequence() -> None:
    buyer = Trader("buyer", HoldPolicy())
    seller = Trader("seller", HoldPolicy())
    bundle = _components(traders=(seller, buyer))
    prior = Order(
        order_id="manual-7",
        agent_id="buyer",
        instrument_id="ACME",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        price=Decimal("99"),
        submitted_at=0,
        sequence_number=7,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )
    bundle.exchange.submit(prior)
    model = StaticFinanceModel(seed=7)
    model.bundle = bundle
    model.setup()

    assert model.next_order_sequence == 8
    assert tuple(trader.agent_id for trader in model.finance.traders) == ("buyer", "seller")


def test_finance_seed_is_call_order_independent_and_cached() -> None:
    first = StaticFinanceModel(seed=123)
    alpha_first = first.finance_seed("alpha")
    beta_first = first.finance_seed("beta")
    assert first.finance_seed("alpha") == alpha_first

    second = StaticFinanceModel(seed=123)
    beta_second = second.finance_seed("beta")
    alpha_second = second.finance_seed("alpha")
    assert (alpha_first, beta_first) == (alpha_second, beta_second)
    assert alpha_first != beta_first


def test_finance_seed_requires_explicit_model_seed() -> None:
    model = StaticFinanceModel(seed=None)
    with pytest.raises(FinanceSeedUnavailableError):
        model.finance_seed("noise")


def test_setup_rejects_clock_drift() -> None:
    trader = Trader("agent", HoldPolicy())
    model = StaticFinanceModel(seed=1)
    model.bundle = _components(traders=(trader,), clock_step=1)
    with pytest.raises(FinanceClockDriftError):
        model.setup()


def test_setup_rejects_unregistered_trader() -> None:
    trader = Trader("missing", HoldPolicy())
    instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
    model = StaticFinanceModel(seed=1)
    model.bundle = FinanceComponents(
        exchange=Exchange(instrument),
        clock=MarketClock(),
        fundamental=ConstantFundamentalValue(Decimal("100")),
        traders=(trader,),
    )
    with pytest.raises(InvalidFinanceComponentsError):
        model.setup()


def test_expected_policy_rejection_consumes_adapter_identity_without_market_mutation() -> None:
    rejected = Trader("a-rejected", InvalidTickThenLimitPolicy(Decimal("99.5")))
    accepted = Trader("b-accepted", InvalidTickThenLimitPolicy(Decimal("99")))
    bundle = _components(traders=(accepted, rejected))
    model = StaticFinanceModel(seed=9)
    model.bundle = bundle
    model.setup()

    model._run_for(1, finalize=False)
    result = model.last_finance_step
    assert result is not None
    assert result.rejection_count == 1
    assert result.trade_count == 0
    assert model.next_order_sequence == 2
    assert bundle.exchange.order("finance-order-000000000000") is None
    rested = bundle.exchange.order("finance-order-000000000001")
    assert rested is not None
    assert rested.agent_id == "b-accepted"
    assert model.steps == 1
    assert bundle.clock.current_step == 1


def test_manual_step_without_abmforge_step_increment_detects_clock_drift() -> None:
    trader = Trader("agent", HoldPolicy())
    model = StaticFinanceModel(seed=1)
    model.bundle = _components(traders=(trader,))
    model.setup()
    model.step()
    with pytest.raises(FinanceClockDriftError):
        model.step()


class BuyLimitPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.limit(Side.BUY, Decimal("1"), Decimal("99"))


class CaptureHoldPolicy:
    def __init__(self) -> None:
        self.best_bids: list[Decimal | None] = []

    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del agent_id
        self.best_bids.append(observation.best_bid)
        return TradingDecision.hold()


def test_all_policies_observe_common_pre_action_market_snapshot() -> None:
    observer_policy = CaptureHoldPolicy()
    maker = Trader("a-maker", BuyLimitPolicy())
    observer = Trader("b-observer", observer_policy)
    bundle = _components(traders=(observer, maker))
    model = StaticFinanceModel(seed=12)
    model.bundle = bundle
    model.setup()

    model._run_for(1, finalize=False)

    assert observer_policy.best_bids == [None]
    assert bundle.exchange.snapshot().best_bid == Decimal("99")


def test_execution_order_and_order_identity_follow_sorted_agent_id() -> None:
    first = Trader("z-agent", BuyLimitPolicy())
    second = Trader("a-agent", BuyLimitPolicy())
    bundle = _components(traders=(first, second))
    model = StaticFinanceModel(seed=12)
    model.bundle = bundle
    model.setup()

    model._run_for(1, finalize=False)
    result = model.last_finance_step
    assert result is not None
    assert tuple(outcome.agent_id for outcome in result.outcomes) == ("a-agent", "z-agent")
    assert tuple(outcome.order.sequence_number for outcome in result.outcomes if outcome.order) == (
        0,
        1,
    )


def test_setup_may_only_run_once() -> None:
    trader = Trader("agent", HoldPolicy())
    model = StaticFinanceModel(seed=1)
    model.bundle = _components(traders=(trader,))
    model.setup()
    with pytest.raises(InvalidFinanceComponentsError):
        model.setup()


def test_finance_seed_rejects_blank_name() -> None:
    model = StaticFinanceModel(seed=1)
    with pytest.raises(ValueError):
        model.finance_seed("   ")


@pytest.mark.parametrize(
    "bundle",
    [
        object(),
        FinanceComponents(
            exchange=cast(Any, object()),
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=(),
        ),
        FinanceComponents(
            exchange=Exchange(Instrument("ACME", Decimal("1"), Decimal("1"))),
            clock=cast(Any, object()),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=(),
        ),
        FinanceComponents(
            exchange=Exchange(Instrument("ACME", Decimal("1"), Decimal("1"))),
            clock=MarketClock(),
            fundamental=cast(Any, object()),
            traders=(),
        ),
        FinanceComponents(
            exchange=Exchange(Instrument("ACME", Decimal("1"), Decimal("1"))),
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=cast(Any, []),
        ),
    ],
)
def test_setup_rejects_invalid_component_shapes(bundle: object) -> None:
    model = StaticFinanceModel(seed=1)
    model.bundle = cast(Any, bundle)
    with pytest.raises(InvalidFinanceComponentsError):
        model.setup()


def test_setup_rejects_duplicate_trader_ids() -> None:
    first = Trader("same", HoldPolicy())
    second = Trader("same", HoldPolicy())
    instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
    exchange = Exchange(instrument)
    exchange.register(Account("same", Decimal("100")), Portfolio("same"))
    model = StaticFinanceModel(seed=1)
    model.bundle = FinanceComponents(
        exchange=exchange,
        clock=MarketClock(),
        fundamental=ConstantFundamentalValue(Decimal("100")),
        traders=(first, second),
    )
    with pytest.raises(InvalidFinanceComponentsError):
        model.setup()


def test_setup_rejects_exchange_time_ahead_of_clock() -> None:
    trader = Trader("agent", HoldPolicy())
    instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
    exchange = Exchange(instrument)
    exchange.register(Account("agent", Decimal("1000")), Portfolio("agent"))
    exchange.submit(
        Order(
            order_id="future",
            agent_id="agent",
            instrument_id="ACME",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            remaining_quantity=Decimal("1"),
            price=Decimal("99"),
            submitted_at=1,
            sequence_number=0,
            time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
        )
    )
    model = StaticFinanceModel(seed=1)
    model.bundle = FinanceComponents(
        exchange=exchange,
        clock=MarketClock(),
        fundamental=ConstantFundamentalValue(Decimal("100")),
        traders=(trader,),
    )
    with pytest.raises(FinanceClockDriftError):
        model.setup()


def test_hold_decision_cannot_be_converted_to_order() -> None:
    trader = Trader("agent", HoldPolicy())
    model = StaticFinanceModel(seed=1)
    model.bundle = _components(traders=(trader,))
    model.setup()
    with pytest.raises(ValueError):
        model._order_from_decision(
            agent_id="agent",
            decision=TradingDecision.hold(),
            period=0,
        )
