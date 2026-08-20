"""Property tests for exchange atomicity, conservation, and exact replay."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import (
    Account,
    Exchange,
    Instrument,
    InsufficientBuyingPowerError,
    Order,
    OrderType,
    Portfolio,
    Side,
    TimeInForce,
)

_POSITIVE = st.integers(min_value=1, max_value=50)


def make_exchange(*, buyer_cash: Decimal, seller_inventory: Decimal) -> Exchange:
    exchange = Exchange(Instrument("ACME", Decimal("0.01"), Decimal("1")))
    exchange.register(Account("buyer", buyer_cash), Portfolio("buyer"))
    exchange.register(
        Account("seller", Decimal("0")),
        Portfolio("seller", (("ACME", seller_inventory),)),
    )
    return exchange


def limit_order(
    order_id: str,
    agent_id: str,
    *,
    side: Side,
    quantity: Decimal,
    price: Decimal,
    sequence_number: int,
    submitted_at: int,
) -> Order:
    return Order(
        order_id=order_id,
        agent_id=agent_id,
        instrument_id="ACME",
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        remaining_quantity=quantity,
        price=price,
        submitted_at=submitted_at,
        sequence_number=sequence_number,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )


def market_buy(*, quantity: Decimal) -> Order:
    return Order(
        order_id="market-buy",
        agent_id="buyer",
        instrument_id="ACME",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity,
        remaining_quantity=quantity,
        price=None,
        submitted_at=1,
        sequence_number=1,
        time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
    )


@given(price=_POSITIVE, quantity=_POSITIVE)
def test_committed_execution_conserves_cash_and_inventory(price: int, quantity: int) -> None:
    execution_price = Decimal(price)
    execution_quantity = Decimal(quantity)
    initial_cash = execution_price * execution_quantity + Decimal("10")
    exchange = make_exchange(
        buyer_cash=initial_cash,
        seller_inventory=execution_quantity + Decimal("10"),
    )
    exchange.submit(
        limit_order(
            "ask",
            "seller",
            side=Side.SELL,
            quantity=execution_quantity,
            price=execution_price,
            sequence_number=0,
            submitted_at=0,
        )
    )
    cash_before = exchange.account("buyer").cash + exchange.account("seller").cash
    inventory_before = exchange.portfolio("buyer").quantity("ACME") + exchange.portfolio(
        "seller"
    ).quantity("ACME")

    exchange.submit(market_buy(quantity=execution_quantity))

    cash_after = (
        exchange.account("buyer").cash + exchange.account("seller").cash + exchange.fee_balance
    )
    inventory_after = exchange.portfolio("buyer").quantity("ACME") + exchange.portfolio(
        "seller"
    ).quantity("ACME")
    assert cash_after == cash_before
    assert inventory_after == inventory_before


@given(price=_POSITIVE, first_quantity=_POSITIVE, second_quantity=_POSITIVE)
def test_resting_buy_commitment_boundary_is_atomic(
    price: int,
    first_quantity: int,
    second_quantity: int,
) -> None:
    limit_price = Decimal(price)
    first = Decimal(first_quantity)
    second = Decimal(second_quantity)
    required_first = limit_price * first
    total_required = limit_price * (first + second)
    buyer_cash = required_first + (limit_price * second / Decimal("2"))
    exchange = make_exchange(buyer_cash=buyer_cash, seller_inventory=Decimal("100000"))
    exchange.submit(
        limit_order(
            "buy-1",
            "buyer",
            side=Side.BUY,
            quantity=first,
            price=limit_price,
            sequence_number=0,
            submitted_at=0,
        )
    )
    before = exchange.snapshot()
    second_order = limit_order(
        "buy-2",
        "buyer",
        side=Side.BUY,
        quantity=second,
        price=limit_price,
        sequence_number=1,
        submitted_at=1,
    )

    assert buyer_cash < total_required
    try:
        exchange.submit(second_order)
    except InsufficientBuyingPowerError:
        pass
    else:  # pragma: no cover - the generated construction always overcommits
        raise AssertionError("overcommitted resting buy unexpectedly succeeded")

    assert exchange.snapshot() == before
    assert exchange.order("buy-2") is None


@given(price=_POSITIVE, quantity=_POSITIVE)
def test_identical_exchange_inputs_replay_exactly(price: int, quantity: int) -> None:
    execution_price = Decimal(price)
    execution_quantity = Decimal(quantity)
    starting_cash = execution_price * execution_quantity + Decimal("100")
    exchanges = [
        make_exchange(
            buyer_cash=starting_cash,
            seller_inventory=execution_quantity + Decimal("10"),
        )
        for _ in range(2)
    ]

    results = []
    for exchange in exchanges:
        exchange.submit(
            limit_order(
                "ask",
                "seller",
                side=Side.SELL,
                quantity=execution_quantity,
                price=execution_price,
                sequence_number=0,
                submitted_at=0,
            )
        )
        results.append(exchange.submit(market_buy(quantity=execution_quantity)))

    first, second = exchanges
    assert results[0] == results[1]
    assert first.snapshot() == second.snapshot()
    assert first.account("buyer") == second.account("buyer")
    assert first.account("seller") == second.account("seller")
    assert first.portfolio("buyer") == second.portfolio("buyer")
    assert first.portfolio("seller") == second.portfolio("seller")
    assert first.settled_trade_ids == second.settled_trade_ids
