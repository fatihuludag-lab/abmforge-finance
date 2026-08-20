"""Deterministic single-instrument matching engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from abmforge_finance.domain import Instrument, Order, OrderType, Side, TimeInForce, Trade
from abmforge_finance.exceptions import (
    DuplicateOrderError,
    DuplicateSequenceNumberError,
    InvalidIncomingOrderError,
)
from abmforge_finance.market.order_book import LimitOrderBook

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Represent the deterministic outcome of one submitted order.

    Parameters
    ----------
    final_order
        Immutable incoming-order state after all executions.
    trades
        Executions produced in deterministic price-time order.
    rested
        Whether the positive unfilled remainder was placed in the resting book.

    Notes
    -----
    A positive remainder with ``rested=False`` is the cancelled IOC residual. A filled
    order always has zero remaining quantity and never rests.
    """

    final_order: Order
    trades: tuple[Trade, ...]
    rested: bool

    @property
    def executed_quantity(self) -> Decimal:
        """Return the exact quantity executed from the incoming order."""
        return self.final_order.filled_quantity

    @property
    def unfilled_quantity(self) -> Decimal:
        """Return the exact final unfilled quantity."""
        return self.final_order.remaining_quantity

    @property
    def cancelled_quantity(self) -> Decimal:
        """Return the IOC residual cancelled rather than rested."""
        if self.rested or self.final_order.is_filled:
            return _ZERO
        return self.final_order.remaining_quantity

    @property
    def resting_order_id(self) -> str | None:
        """Return the active residual order identifier, if one rests."""
        return self.final_order.order_id if self.rested else None


class MatchingEngine:
    """Match incoming orders against one deterministic central limit order book.

    The engine owns a fresh :class:`LimitOrderBook` for one instrument. Incoming
    submissions are processed synchronously in explicit event order. Resting maker
    orders receive their own limit price; the incoming order is always the taker.

    Parameters
    ----------
    instrument
        Instrument whose exact tick and lot grids govern matching.

    Raises
    ------
    TypeError
        If ``instrument`` is not an :class:`Instrument`.

    Determinism
    -----------
    Accepted submissions must have non-decreasing ``submitted_at`` values and strictly
    increasing ``sequence_number`` values. Trade sequences start at zero and increase
    contiguously. Trade identifiers are derived only from those sequence numbers.
    """

    __slots__ = (
        "_book",
        "_last_sequence_number",
        "_last_submitted_at",
        "_next_trade_sequence",
        "_seen_order_ids",
        "_seen_sequence_numbers",
    )

    def __init__(self, instrument: Instrument) -> None:
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        self._book = LimitOrderBook(instrument)
        self._seen_order_ids: set[str] = set()
        self._seen_sequence_numbers: set[int] = set()
        self._last_submitted_at: int | float | None = None
        self._last_sequence_number: int | None = None
        self._next_trade_sequence = 0

    @property
    def instrument(self) -> Instrument:
        """Return the instrument matched by this engine."""
        return self._book.instrument

    @property
    def book(self) -> LimitOrderBook:
        """Return the owned resting book for inspection and cancellation."""
        return self._book

    @property
    def next_trade_sequence(self) -> int:
        """Return the deterministic sequence number assigned to the next trade."""
        return self._next_trade_sequence

    def submit(self, order: Order) -> MatchResult:
        """Process one fresh incoming order synchronously.

        Parameters
        ----------
        order
            Fresh market or limit order for this engine's instrument.

        Returns
        -------
        MatchResult
            Immutable executions, final incoming-order state, and resting disposition.

        Raises
        ------
        InvalidIncomingOrderError
            If the order is not fresh, targets another instrument, violates the exact
            price/quantity grids, or arrives out of explicit event order.
        DuplicateOrderError
            If an incoming order identifier has already been submitted to this engine.
        DuplicateSequenceNumberError
            If a submission sequence number has already been used.

        Notes
        -----
        Market orders and IOC limits never rest. A positive residual from a GTC limit
        rests after all price-compatible makers have been consumed. Expected input
        validation is completed before resting-book mutation begins.
        """
        self._validate_incoming(order)
        planned_trades, final_order, rested = self._plan(order)

        for trade in planned_trades:
            self._book.apply_fill(trade.maker_order_id, trade.quantity)

        if rested:
            self._book.add(final_order)

        self._seen_order_ids.add(order.order_id)
        self._seen_sequence_numbers.add(order.sequence_number)
        self._last_submitted_at = order.submitted_at
        self._last_sequence_number = order.sequence_number
        self._next_trade_sequence += len(planned_trades)

        return MatchResult(final_order=final_order, trades=planned_trades, rested=rested)

    def _validate_incoming(self, order: Order) -> None:
        if not isinstance(order, Order):
            raise InvalidIncomingOrderError("order must be an Order")
        if order.order_id in self._seen_order_ids:
            raise DuplicateOrderError(f"order_id {order.order_id!r} has already been submitted")
        if order.sequence_number in self._seen_sequence_numbers:
            raise DuplicateSequenceNumberError(
                f"sequence_number {order.sequence_number} has already been submitted"
            )
        if order.instrument_id != self.instrument.instrument_id:
            raise InvalidIncomingOrderError(
                f"order instrument {order.instrument_id!r} does not match engine instrument "
                f"{self.instrument.instrument_id!r}"
            )
        if order.remaining_quantity != order.quantity:
            raise InvalidIncomingOrderError(
                "incoming orders must be fresh with remaining_quantity equal to quantity"
            )

        self.instrument.validate_quantity(order.quantity)
        if order.order_type is OrderType.LIMIT:
            self.instrument.validate_price(cast(Decimal, order.price))

        if self._last_submitted_at is not None and order.submitted_at < self._last_submitted_at:
            raise InvalidIncomingOrderError("submitted_at cannot move backwards within one engine")
        if (
            self._last_sequence_number is not None
            and order.sequence_number <= self._last_sequence_number
        ):
            raise InvalidIncomingOrderError(
                "sequence_number must increase strictly across accepted submissions"
            )

    def _plan(self, order: Order) -> tuple[tuple[Trade, ...], Order, bool]:
        remaining = order.remaining_quantity
        trades: list[Trade] = []
        opposite_side = order.side.opposite

        for maker in self._book.orders_by_priority(opposite_side):
            if remaining == _ZERO:
                break
            maker_price = cast(Decimal, maker.price)
            if not self._price_compatible(order, maker_price):
                break

            quantity = min(remaining, maker.remaining_quantity)
            trades.append(
                self._make_trade(
                    incoming=order,
                    maker=maker,
                    price=maker_price,
                    quantity=quantity,
                    trade_sequence=self._next_trade_sequence + len(trades),
                )
            )
            remaining -= quantity

        final_order = order.with_remaining_quantity(remaining)
        rested = (
            remaining > _ZERO
            and order.order_type is OrderType.LIMIT
            and order.time_in_force is TimeInForce.GOOD_TIL_CANCELLED
        )
        return tuple(trades), final_order, rested

    @staticmethod
    def _price_compatible(order: Order, maker_price: Decimal) -> bool:
        if order.order_type is OrderType.MARKET:
            return True
        limit_price = cast(Decimal, order.price)
        if order.side is Side.BUY:
            return maker_price <= limit_price
        return maker_price >= limit_price

    @staticmethod
    def _make_trade(
        *,
        incoming: Order,
        maker: Order,
        price: Decimal,
        quantity: Decimal,
        trade_sequence: int,
    ) -> Trade:
        if incoming.side is Side.BUY:
            buy_order = incoming
            sell_order = maker
        else:
            buy_order = maker
            sell_order = incoming

        return Trade(
            trade_id=f"trade-{trade_sequence:012d}",
            instrument_id=incoming.instrument_id,
            buy_order_id=buy_order.order_id,
            sell_order_id=sell_order.order_id,
            buyer_id=buy_order.agent_id,
            seller_id=sell_order.agent_id,
            price=price,
            quantity=quantity,
            executed_at=incoming.submitted_at,
            sequence_number=trade_sequence,
            maker_order_id=maker.order_id,
            taker_order_id=incoming.order_id,
        )
