"""Property tests for clearing conservation and deterministic replay."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import Account, ClearingEngine, Portfolio, Trade

_POSITIVE = st.integers(min_value=1, max_value=100)
_FEE = st.integers(min_value=-5, max_value=5)


def make_trade(
    *,
    price: int,
    quantity: int,
    buyer_fee: int,
    seller_fee: int,
    sequence_number: int,
) -> Trade:
    trade_id = f"trade-{sequence_number}"
    return Trade(
        trade_id=trade_id,
        instrument_id="ACME",
        buy_order_id=f"buy-{trade_id}",
        sell_order_id=f"sell-{trade_id}",
        buyer_id="buyer",
        seller_id="seller",
        price=Decimal(price),
        quantity=Decimal(quantity),
        executed_at=sequence_number,
        sequence_number=sequence_number,
        maker_order_id=f"sell-{trade_id}",
        taker_order_id=f"buy-{trade_id}",
        buyer_fee=Decimal(buyer_fee),
        seller_fee=Decimal(seller_fee),
    )


def engine_for(trade: Trade) -> ClearingEngine:
    engine = ClearingEngine(allow_short_selling=False)
    required_buyer_cash = max(Decimal("0"), trade.notional + trade.buyer_fee)
    required_seller_cash = max(Decimal("0"), trade.seller_fee - trade.notional)
    engine.register(Account("buyer", required_buyer_cash + Decimal("10")), Portfolio("buyer"))
    engine.register(
        Account("seller", required_seller_cash + Decimal("10")),
        Portfolio("seller", (("ACME", trade.quantity + Decimal("10")),)),
    )
    return engine


@given(price=_POSITIVE, quantity=_POSITIVE, buyer_fee=_FEE, seller_fee=_FEE)
def test_settlement_conserves_cash_plus_fees_and_inventory(
    price: int,
    quantity: int,
    buyer_fee: int,
    seller_fee: int,
) -> None:
    trade = make_trade(
        price=price,
        quantity=quantity,
        buyer_fee=buyer_fee,
        seller_fee=seller_fee,
        sequence_number=0,
    )
    engine = engine_for(trade)
    initial_cash = engine.account("buyer").cash + engine.account("seller").cash
    initial_inventory = engine.portfolio("buyer").quantity("ACME") + engine.portfolio(
        "seller"
    ).quantity("ACME")

    engine.settle(trade)

    final_cash = engine.account("buyer").cash + engine.account("seller").cash
    final_inventory = engine.portfolio("buyer").quantity("ACME") + engine.portfolio(
        "seller"
    ).quantity("ACME")
    assert final_cash + engine.fee_balance == initial_cash
    assert final_inventory == initial_inventory


@given(price=_POSITIVE, quantity=_POSITIVE, buyer_fee=_FEE, seller_fee=_FEE)
def test_identical_settlement_inputs_replay_exactly(
    price: int,
    quantity: int,
    buyer_fee: int,
    seller_fee: int,
) -> None:
    trade = make_trade(
        price=price,
        quantity=quantity,
        buyer_fee=buyer_fee,
        seller_fee=seller_fee,
        sequence_number=0,
    )
    left = engine_for(trade)
    right = engine_for(trade)

    left_result = left.settle(trade)
    right_result = right.settle(trade)

    assert left_result == right_result
    assert left.account("buyer") == right.account("buyer")
    assert left.account("seller") == right.account("seller")
    assert left.portfolio("buyer") == right.portfolio("buyer")
    assert left.portfolio("seller") == right.portfolio("seller")
    assert left.fee_balance == right.fee_balance
    assert left.settled_trade_ids == right.settled_trade_ids
