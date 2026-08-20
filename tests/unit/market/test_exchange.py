"""Unit tests for atomic single-instrument exchange orchestration."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    Account,
    Exchange,
    Instrument,
    InsufficientAvailableInventoryError,
    InsufficientBuyingPowerError,
    InvalidIncomingOrderError,
    Order,
    OrderNotFoundError,
    OrderOwnershipError,
    OrderType,
    Portfolio,
    Side,
    TimeInForce,
    UnknownParticipantError,
)


def instrument() -> Instrument:
    return Instrument("ACME", Decimal("0.01"), Decimal("1"))


def order(
    order_id: str,
    agent_id: str,
    *,
    side: Side,
    sequence_number: int,
    quantity: str = "1",
    price: str = "100.00",
    order_type: OrderType = OrderType.LIMIT,
    tif: TimeInForce = TimeInForce.GOOD_TIL_CANCELLED,
    submitted_at: int = 0,
) -> Order:
    resolved_price = None if order_type is OrderType.MARKET else Decimal(price)
    return Order(
        order_id=order_id,
        agent_id=agent_id,
        instrument_id="ACME",
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        remaining_quantity=Decimal(quantity),
        price=resolved_price,
        submitted_at=submitted_at,
        sequence_number=sequence_number,
        time_in_force=tif,
    )


def registered_exchange(*, allow_short_selling: bool = False) -> Exchange:
    exchange = Exchange(instrument(), allow_short_selling=allow_short_selling)
    exchange.register(Account("buyer", Decimal("1000")), Portfolio("buyer"))
    exchange.register(
        Account("seller", Decimal("100")),
        Portfolio("seller", (("ACME", Decimal("20")),)),
    )
    return exchange


def test_constructor_validates_inputs() -> None:
    with pytest.raises(TypeError):
        Exchange(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Exchange(instrument(), allow_short_selling=1)  # type: ignore[arg-type]


def test_register_and_read_participant_state() -> None:
    exchange = Exchange(instrument())
    account = Account("agent", Decimal("10"))
    portfolio = Portfolio("agent", (("ACME", Decimal("2")),))
    exchange.register(account, portfolio)

    assert exchange.account("agent") == account
    assert exchange.portfolio("agent") == portfolio
    assert exchange.snapshot().order_count == 0
    assert exchange.settled_trade_ids == ()
    assert exchange.fee_balance == Decimal("0")


def test_unregistered_participant_cannot_submit_even_when_order_would_not_trade() -> None:
    exchange = Exchange(instrument())
    incoming = order("o-1", "ghost", side=Side.BUY, sequence_number=0)

    with pytest.raises(UnknownParticipantError):
        exchange.submit(incoming)

    assert exchange.snapshot().order_count == 0
    assert exchange.next_trade_sequence == 0


def test_submit_requires_order_instance_without_mutation() -> None:
    exchange = registered_exchange()
    before = exchange.snapshot()

    with pytest.raises(InvalidIncomingOrderError):
        exchange.submit(object())  # type: ignore[arg-type]

    assert exchange.snapshot() == before


def test_funded_gtc_buy_rests_and_is_queryable() -> None:
    exchange = registered_exchange()
    incoming = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=0,
        quantity="4",
        price="100.00",
    )

    result = exchange.submit(incoming)

    assert result.rested is True
    assert result.trades == ()
    assert result.settlements == ()
    assert exchange.order("buy-1") == result.final_order
    assert exchange.snapshot().best_bid == Decimal("100.00")


def test_resting_buy_commitments_prevent_cash_overcommitment_atomically() -> None:
    exchange = registered_exchange()
    first = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=0,
        quantity="6",
        price="100.00",
    )
    second = order(
        "buy-2",
        "buyer",
        side=Side.BUY,
        sequence_number=1,
        quantity="5",
        price="100.00",
        submitted_at=1,
    )
    exchange.submit(first)
    before = exchange.snapshot()

    with pytest.raises(InsufficientBuyingPowerError):
        exchange.submit(second)

    assert exchange.snapshot() == before
    assert exchange.order("buy-2") is None
    assert exchange.next_trade_sequence == 0
    assert exchange.settled_trade_ids == ()


def test_rejected_resting_buy_does_not_consume_order_sequence() -> None:
    exchange = registered_exchange()
    first = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=0,
        quantity="6",
        price="100.00",
    )
    second = order(
        "buy-2",
        "buyer",
        side=Side.BUY,
        sequence_number=1,
        quantity="5",
        price="100.00",
        submitted_at=1,
    )
    exchange.submit(first)
    with pytest.raises(InsufficientBuyingPowerError):
        exchange.submit(second)

    exchange.cancel("buy-1", participant_id="buyer")
    result = exchange.submit(second)

    assert result.rested is True
    assert exchange.order("buy-2") is not None


def test_resting_sell_commitments_prevent_inventory_overcommitment() -> None:
    exchange = registered_exchange()
    first = order(
        "sell-1",
        "seller",
        side=Side.SELL,
        sequence_number=0,
        quantity="12",
        price="101.00",
    )
    second = order(
        "sell-2",
        "seller",
        side=Side.SELL,
        sequence_number=1,
        quantity="9",
        price="102.00",
        submitted_at=1,
    )
    exchange.submit(first)
    before = exchange.snapshot()

    with pytest.raises(InsufficientAvailableInventoryError):
        exchange.submit(second)

    assert exchange.snapshot() == before
    assert exchange.order("sell-2") is None


def test_short_selling_opt_in_allows_unfunded_resting_sell_inventory() -> None:
    exchange = Exchange(instrument(), allow_short_selling=True)
    exchange.register(Account("short", Decimal("100")), Portfolio("short"))
    incoming = order(
        "sell-1",
        "short",
        side=Side.SELL,
        sequence_number=0,
        quantity="10",
        price="101.00",
    )

    result = exchange.submit(incoming)

    assert result.rested is True
    assert exchange.allow_short_selling is True
    assert exchange.order("sell-1") is not None


def test_market_execution_settles_cash_and_inventory() -> None:
    exchange = registered_exchange()
    passive = order(
        "sell-1",
        "seller",
        side=Side.SELL,
        sequence_number=0,
        quantity="4",
        price="99.50",
    )
    aggressive = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=1,
        quantity="4",
        order_type=OrderType.MARKET,
        tif=TimeInForce.IMMEDIATE_OR_CANCEL,
        submitted_at=1,
    )
    exchange.submit(passive)

    result = exchange.submit(aggressive)

    assert len(result.trades) == 1
    assert len(result.settlements) == 1
    assert result.trades[0].price == Decimal("99.50")
    assert exchange.account("buyer").cash == Decimal("602.00")
    assert exchange.portfolio("buyer").quantity("ACME") == Decimal("4")
    assert exchange.account("seller").cash == Decimal("498.00")
    assert exchange.portfolio("seller").quantity("ACME") == Decimal("16")
    assert exchange.order("sell-1") is None
    assert exchange.settled_trade_ids == ("trade-000000000000",)


def test_insufficient_market_buying_power_rolls_back_matching_and_clearing() -> None:
    exchange = Exchange(instrument())
    exchange.register(Account("buyer", Decimal("50")), Portfolio("buyer"))
    exchange.register(
        Account("seller", Decimal("0")),
        Portfolio("seller", (("ACME", Decimal("10")),)),
    )
    passive = order(
        "sell-1",
        "seller",
        side=Side.SELL,
        sequence_number=0,
        quantity="10",
        price="10.00",
    )
    aggressive = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=1,
        quantity="10",
        order_type=OrderType.MARKET,
        tif=TimeInForce.IMMEDIATE_OR_CANCEL,
        submitted_at=1,
    )
    exchange.submit(passive)
    before_book = exchange.snapshot()
    buyer_before = exchange.account("buyer")
    seller_before = exchange.account("seller")

    with pytest.raises(InsufficientBuyingPowerError):
        exchange.submit(aggressive)

    assert exchange.snapshot() == before_book
    assert exchange.account("buyer") == buyer_before
    assert exchange.account("seller") == seller_before
    assert exchange.order("sell-1") is not None
    assert exchange.next_trade_sequence == 0
    assert exchange.settled_trade_ids == ()


def test_insufficient_market_sell_inventory_rolls_back_matching() -> None:
    exchange = Exchange(instrument())
    exchange.register(Account("buyer", Decimal("1000")), Portfolio("buyer"))
    exchange.register(Account("seller", Decimal("0")), Portfolio("seller"))
    passive = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=0,
        quantity="5",
        price="10.00",
    )
    aggressive = order(
        "sell-1",
        "seller",
        side=Side.SELL,
        sequence_number=1,
        quantity="5",
        order_type=OrderType.MARKET,
        tif=TimeInForce.IMMEDIATE_OR_CANCEL,
        submitted_at=1,
    )
    exchange.submit(passive)
    before = exchange.snapshot()

    with pytest.raises(InsufficientAvailableInventoryError):
        exchange.submit(aggressive)

    assert exchange.snapshot() == before
    assert exchange.order("buy-1") is not None
    assert exchange.next_trade_sequence == 0


def test_multilevel_failure_is_all_or_nothing() -> None:
    exchange = Exchange(instrument())
    exchange.register(Account("buyer", Decimal("150")), Portfolio("buyer"))
    for seller_id in ("seller-1", "seller-2"):
        exchange.register(
            Account(seller_id, Decimal("0")),
            Portfolio(seller_id, (("ACME", Decimal("10")),)),
        )
    exchange.submit(
        order(
            "ask-1",
            "seller-1",
            side=Side.SELL,
            sequence_number=0,
            quantity="10",
            price="10.00",
        )
    )
    exchange.submit(
        order(
            "ask-2",
            "seller-2",
            side=Side.SELL,
            sequence_number=1,
            quantity="10",
            price="11.00",
            submitted_at=1,
        )
    )
    before = exchange.snapshot()
    incoming = order(
        "market-buy",
        "buyer",
        side=Side.BUY,
        sequence_number=2,
        quantity="20",
        order_type=OrderType.MARKET,
        tif=TimeInForce.IMMEDIATE_OR_CANCEL,
        submitted_at=2,
    )

    with pytest.raises(InsufficientBuyingPowerError):
        exchange.submit(incoming)

    assert exchange.snapshot() == before
    assert exchange.order("ask-1") is not None
    assert exchange.order("ask-2") is not None
    assert exchange.settled_trade_ids == ()
    assert exchange.next_trade_sequence == 0


def test_partial_cross_then_rest_uses_limit_price_for_residual_commitment() -> None:
    exchange = Exchange(instrument())
    exchange.register(Account("buyer", Decimal("550")), Portfolio("buyer"))
    exchange.register(
        Account("seller", Decimal("0")),
        Portfolio("seller", (("ACME", Decimal("2")),)),
    )
    exchange.submit(
        order(
            "ask-1",
            "seller",
            side=Side.SELL,
            sequence_number=0,
            quantity="2",
            price="90.00",
        )
    )
    incoming = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=1,
        quantity="6",
        price="100.00",
        submitted_at=1,
    )

    with pytest.raises(InsufficientBuyingPowerError):
        exchange.submit(incoming)

    # The two shares could be bought for 180, but the four-share residual would
    # require another 400 at its limit, so the whole staged transaction is rejected.
    assert exchange.account("buyer").cash == Decimal("550")
    assert exchange.order("ask-1") is not None
    assert exchange.order("buy-1") is None


def test_cancel_requires_registered_owner_and_releases_commitment() -> None:
    exchange = registered_exchange()
    incoming = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=0,
        quantity="6",
        price="100.00",
    )
    exchange.submit(incoming)

    with pytest.raises(OrderOwnershipError):
        exchange.cancel("buy-1", participant_id="seller")
    with pytest.raises(UnknownParticipantError):
        exchange.cancel("buy-1", participant_id="ghost")

    cancelled = exchange.cancel("buy-1", participant_id="buyer")
    assert cancelled.order_id == "buy-1"
    assert exchange.order("buy-1") is None


def test_cancel_unknown_order_preserves_standard_order_book_error() -> None:
    exchange = registered_exchange()
    with pytest.raises(OrderNotFoundError):
        exchange.cancel("missing", participant_id="buyer")


def test_no_liquidity_ioc_is_committed_without_financial_change() -> None:
    exchange = Exchange(instrument())
    exchange.register(Account("buyer", Decimal("0")), Portfolio("buyer"))
    incoming = order(
        "buy-1",
        "buyer",
        side=Side.BUY,
        sequence_number=0,
        quantity="5",
        order_type=OrderType.MARKET,
        tif=TimeInForce.IMMEDIATE_OR_CANCEL,
    )

    result = exchange.submit(incoming)

    assert result.executed_quantity == Decimal("0")
    assert result.cancelled_quantity == Decimal("5")
    assert result.trades == ()
    assert exchange.account("buyer").cash == Decimal("0")
    assert exchange.snapshot().order_count == 0


def test_short_seller_can_execute_into_negative_inventory_when_enabled() -> None:
    exchange = Exchange(instrument(), allow_short_selling=True)
    exchange.register(Account("buyer", Decimal("1000")), Portfolio("buyer"))
    exchange.register(Account("seller", Decimal("0")), Portfolio("seller"))
    exchange.submit(
        order(
            "buy-1",
            "buyer",
            side=Side.BUY,
            sequence_number=0,
            quantity="5",
            price="10.00",
        )
    )
    result = exchange.submit(
        order(
            "sell-1",
            "seller",
            side=Side.SELL,
            sequence_number=1,
            quantity="5",
            order_type=OrderType.MARKET,
            tif=TimeInForce.IMMEDIATE_OR_CANCEL,
            submitted_at=1,
        )
    )

    assert result.executed_quantity == Decimal("5")
    assert exchange.portfolio("seller").quantity("ACME") == Decimal("-5")
    assert exchange.account("seller").cash == Decimal("50.00")


def test_exchange_result_convenience_properties_match_matching_result() -> None:
    exchange = registered_exchange()
    result = exchange.submit(
        order(
            "buy-1",
            "buyer",
            side=Side.BUY,
            sequence_number=0,
            quantity="2",
            price="10.00",
        )
    )

    assert result.final_order == result.match_result.final_order
    assert result.trades == result.match_result.trades
    assert result.rested == result.match_result.rested
    assert result.executed_quantity == result.match_result.executed_quantity
    assert result.cancelled_quantity == result.match_result.cancelled_quantity
