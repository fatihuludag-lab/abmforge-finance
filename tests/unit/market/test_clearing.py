"""Unit tests for deterministic clearing and portfolio accounting."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    Account,
    ClearingEngine,
    DuplicateParticipantError,
    DuplicateSettlementError,
    InsufficientCashError,
    InsufficientInventoryError,
    InvalidClearingRegistrationError,
    OutOfOrderSettlementError,
    Portfolio,
    Trade,
    UnknownParticipantError,
)


def make_trade(
    *,
    trade_id: str = "trade-1",
    buyer_id: str = "buyer",
    seller_id: str = "seller",
    price: str = "10",
    quantity: str = "2",
    buyer_fee: str = "0",
    seller_fee: str = "0",
    executed_at: int = 1,
    sequence_number: int = 0,
) -> Trade:
    return Trade(
        trade_id=trade_id,
        instrument_id="ACME",
        buy_order_id=f"buy-{trade_id}",
        sell_order_id=f"sell-{trade_id}",
        buyer_id=buyer_id,
        seller_id=seller_id,
        price=Decimal(price),
        quantity=Decimal(quantity),
        executed_at=executed_at,
        sequence_number=sequence_number,
        maker_order_id=f"sell-{trade_id}",
        taker_order_id=f"buy-{trade_id}",
        buyer_fee=Decimal(buyer_fee),
        seller_fee=Decimal(seller_fee),
    )


def registered_engine(*, allow_short_selling: bool = False) -> ClearingEngine:
    engine = ClearingEngine(allow_short_selling=allow_short_selling)
    engine.register(Account("buyer", Decimal("100")), Portfolio("buyer"))
    engine.register(
        Account("seller", Decimal("10")),
        Portfolio("seller", (("ACME", Decimal("10")),)),
    )
    return engine


def snapshot(engine: ClearingEngine) -> tuple[Account, Portfolio, Account, Portfolio, Decimal]:
    return (
        engine.account("buyer"),
        engine.portfolio("buyer"),
        engine.account("seller"),
        engine.portfolio("seller"),
        engine.fee_balance,
    )


def test_constructor_requires_boolean_short_selling_flag() -> None:
    with pytest.raises(TypeError):
        ClearingEngine(allow_short_selling=1)  # type: ignore[arg-type]


def test_register_creates_empty_portfolio_by_default() -> None:
    engine = ClearingEngine()
    account = Account("buyer", Decimal("10"))
    engine.register(account)
    assert engine.account("buyer") is account
    assert engine.portfolio("buyer") == Portfolio("buyer")


def test_register_rejects_duplicate_and_inconsistent_state() -> None:
    engine = ClearingEngine()
    engine.register(Account("buyer", Decimal("10")))
    with pytest.raises(DuplicateParticipantError):
        engine.register(Account("buyer", Decimal("20")))

    other = ClearingEngine()
    with pytest.raises(InvalidClearingRegistrationError):
        other.register(Account("buyer", Decimal("-1")))
    with pytest.raises(InvalidClearingRegistrationError):
        other.register(Account("buyer", Decimal("1")), Portfolio("seller"))
    with pytest.raises(InvalidClearingRegistrationError):
        other.register(Account("buyer", Decimal("1")), object())  # type: ignore[arg-type]
    with pytest.raises(InvalidClearingRegistrationError):
        other.register(object())  # type: ignore[arg-type]


def test_negative_registered_inventory_requires_short_selling() -> None:
    portfolio = Portfolio("seller", (("ACME", Decimal("-1")),))
    with pytest.raises(InvalidClearingRegistrationError):
        ClearingEngine().register(Account("seller", Decimal("10")), portfolio)

    engine = ClearingEngine(allow_short_selling=True)
    engine.register(Account("seller", Decimal("10")), portfolio)
    assert engine.portfolio("seller").quantity("ACME") == Decimal("-1")


def test_unknown_participant_lookup_is_typed() -> None:
    engine = ClearingEngine()
    with pytest.raises(UnknownParticipantError):
        engine.account("missing")
    with pytest.raises(UnknownParticipantError):
        engine.portfolio([])  # type: ignore[arg-type]


def test_settle_transfers_cash_and_inventory_exactly() -> None:
    engine = registered_engine()
    result = engine.settle(make_trade())

    assert engine.account("buyer").cash == Decimal("80")
    assert engine.account("seller").cash == Decimal("30")
    assert engine.portfolio("buyer").quantity("ACME") == Decimal("2")
    assert engine.portfolio("seller").quantity("ACME") == Decimal("8")
    assert engine.fee_balance == Decimal("0")
    assert engine.settled_trade_ids == ("trade-1",)
    assert result.notional == Decimal("20")
    assert result.participant_cash_delta == Decimal("0")
    assert result.inventory_delta == Decimal("0")


def test_signed_fees_and_rebates_flow_through_venue_balance() -> None:
    engine = registered_engine()
    result = engine.settle(make_trade(buyer_fee="1.5", seller_fee="-0.5"))

    assert engine.account("buyer").cash == Decimal("78.5")
    assert engine.account("seller").cash == Decimal("30.5")
    assert engine.fee_balance == Decimal("1.0")
    assert result.buyer_cash_delta == Decimal("-21.5")
    assert result.seller_cash_delta == Decimal("20.5")
    assert result.fee_delta == Decimal("1.0")
    assert result.participant_cash_delta + result.fee_delta == Decimal("0")


def test_duplicate_settlement_is_rejected_without_mutation() -> None:
    engine = registered_engine()
    trade = make_trade()
    engine.settle(trade)
    before = snapshot(engine)
    with pytest.raises(DuplicateSettlementError):
        engine.settle(trade)
    assert snapshot(engine) == before


def test_unknown_trade_participant_is_rejected_without_mutation() -> None:
    engine = registered_engine()
    before = snapshot(engine)
    with pytest.raises(UnknownParticipantError):
        engine.settle(make_trade(buyer_id="missing"))
    assert snapshot(engine) == before


def test_insufficient_cash_is_rejected_atomically() -> None:
    engine = registered_engine()
    before = snapshot(engine)
    with pytest.raises(InsufficientCashError):
        engine.settle(make_trade(price="60", quantity="2"))
    assert snapshot(engine) == before
    assert engine.settled_trade_ids == ()


def test_insufficient_inventory_is_rejected_atomically() -> None:
    engine = registered_engine()
    before = snapshot(engine)
    with pytest.raises(InsufficientInventoryError):
        engine.settle(make_trade(price="1", quantity="11"))
    assert snapshot(engine) == before
    assert engine.settled_trade_ids == ()


def test_short_selling_can_be_enabled_explicitly() -> None:
    engine = registered_engine(allow_short_selling=True)
    engine.settle(make_trade(price="1", quantity="11"))
    assert engine.portfolio("seller").quantity("ACME") == Decimal("-1")


def test_self_trade_nets_notional_and_inventory_but_applies_fees() -> None:
    engine = ClearingEngine()
    engine.register(
        Account("same", Decimal("10")),
        Portfolio("same", (("ACME", Decimal("3")),)),
    )
    trade = make_trade(
        buyer_id="same",
        seller_id="same",
        price="100",
        quantity="2",
        buyer_fee="1",
        seller_fee="2",
    )
    result = engine.settle(trade)
    assert engine.account("same").cash == Decimal("7")
    assert engine.portfolio("same").quantity("ACME") == Decimal("3")
    assert engine.fee_balance == Decimal("3")
    assert result.inventory_delta == Decimal("0")


def test_large_seller_fee_can_trigger_cash_constraint_atomically() -> None:
    engine = registered_engine()
    before = snapshot(engine)
    with pytest.raises(InsufficientCashError):
        engine.settle(make_trade(price="1", quantity="1", seller_fee="20"))
    assert snapshot(engine) == before


def test_settlement_order_must_be_monotone() -> None:
    engine = registered_engine()
    engine.settle(make_trade(trade_id="t-1", executed_at=2, sequence_number=2))
    before = snapshot(engine)

    with pytest.raises(OutOfOrderSettlementError):
        engine.settle(make_trade(trade_id="t-2", executed_at=1, sequence_number=3))
    assert snapshot(engine) == before

    with pytest.raises(OutOfOrderSettlementError):
        engine.settle(make_trade(trade_id="t-3", executed_at=2, sequence_number=2))
    assert snapshot(engine) == before


def test_settled_trade_ids_preserve_accepted_order() -> None:
    engine = registered_engine()
    engine.settle(make_trade(trade_id="trade-10", executed_at=1, sequence_number=1))
    engine.settle(make_trade(trade_id="trade-2", executed_at=2, sequence_number=2))
    assert engine.settled_trade_ids == ("trade-10", "trade-2")


def test_settle_requires_trade_instance() -> None:
    engine = registered_engine()
    with pytest.raises(TypeError):
        engine.settle(object())  # type: ignore[arg-type]
