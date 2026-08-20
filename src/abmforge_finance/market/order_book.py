"""Deterministic resting limit-order-book state and depth queries."""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from abmforge_finance.domain import Instrument, Order, OrderType, Side, TimeInForce
from abmforge_finance.exceptions import (
    CrossingOrderError,
    DuplicateOrderError,
    DuplicateSequenceNumberError,
    InvalidBookOrderError,
    InvalidDepthError,
    OrderBookInvariantError,
    OrderNotFoundError,
    OverfillError,
)

_ZERO = Decimal("0")
_TWO = Decimal("2")


@dataclass(frozen=True, slots=True)
class DepthLevel:
    """Represent one aggregated price level in a depth snapshot.

    Parameters
    ----------
    side
        Side of the book represented by the level.
    price
        Exact public price as ``Decimal``.
    price_ticks
        Integer price-grid coordinate used internally by the book.
    total_quantity
        Sum of all active remaining quantities at the level.
    order_count
        Number of active orders at the level.

    Determinism
    -----------
    Instances are immutable and are produced from explicit price-time-priority state.
    """

    side: Side
    price: Decimal
    price_ticks: int
    total_quantity: Decimal
    order_count: int


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """Capture an immutable aggregate view of one order book.

    Parameters
    ----------
    instrument_id
        Identifier of the book's instrument.
    bids, asks
        Aggregated levels in best-to-worst order.
    best_bid, best_ask
        Best quoted prices, or ``None`` when that side is empty.
    spread, mid_price
        Two-sided quote statistics, or ``None`` when either side is empty.
    imbalance
        Depth imbalance in ``[-1, 1]``, or ``None`` for an empty snapshot.
    order_count
        Number of active resting orders in the full book.

    Determinism
    -----------
    Equal book state and equal depth limits produce equal snapshots.
    """

    instrument_id: str
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]
    best_bid: Decimal | None
    best_ask: Decimal | None
    spread: Decimal | None
    mid_price: Decimal | None
    imbalance: Decimal | None
    order_count: int


class LimitOrderBook:
    """Store non-marketable GTC limit orders using price-time priority.

    The class owns resting-book state only. It does not create trades, select execution
    prices, mutate portfolios, or accept marketable orders. A future matching engine
    will consume incoming orders, apply fills through :meth:`apply_fill`, and place only
    eligible remainders through :meth:`add`.

    Parameters
    ----------
    instrument
        Instrument whose tick and lot grids define valid book entries.

    Raises
    ------
    TypeError
        If ``instrument`` is not an :class:`Instrument`.

    Determinism
    -----------
    Price levels are keyed by integer ticks. Within a level, orders are sorted by
    ``(submitted_at, sequence_number)``. Submission call order therefore cannot change
    priority when the same valid order set is supplied.

    Examples
    --------
    >>> from decimal import Decimal
    >>> from abmforge_finance import Instrument, LimitOrderBook
    >>> book = LimitOrderBook(Instrument("ACME", Decimal("0.01"), Decimal("1")))
    >>> book.best_bid is None
    True
    """

    __slots__ = (
        "_instrument",
        "_levels",
        "_orders",
        "_prices",
        "_seen_order_ids",
        "_seen_sequence_numbers",
    )

    def __init__(self, instrument: Instrument) -> None:
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        self._instrument = instrument
        self._orders: dict[str, Order] = {}
        self._prices: dict[Side, list[int]] = {Side.BUY: [], Side.SELL: []}
        self._levels: dict[Side, dict[int, list[str]]] = {
            Side.BUY: {},
            Side.SELL: {},
        }
        self._seen_order_ids: set[str] = set()
        self._seen_sequence_numbers: set[int] = set()

    @property
    def instrument(self) -> Instrument:
        """Return the immutable instrument definition used by this book."""
        return self._instrument

    @property
    def order_count(self) -> int:
        """Return the number of active resting orders."""
        return len(self._orders)

    @property
    def best_bid(self) -> Decimal | None:
        """Return the highest active bid price, or ``None`` when bids are empty."""
        prices = self._prices[Side.BUY]
        return None if not prices else self._instrument.ticks_to_price(prices[-1])

    @property
    def best_ask(self) -> Decimal | None:
        """Return the lowest active ask price, or ``None`` when asks are empty."""
        prices = self._prices[Side.SELL]
        return None if not prices else self._instrument.ticks_to_price(prices[0])

    @property
    def spread(self) -> Decimal | None:
        """Return ``best_ask - best_bid``, or ``None`` without a two-sided quote."""
        best_bid = self.best_bid
        best_ask = self.best_ask
        if best_bid is None or best_ask is None:
            return None
        return best_ask - best_bid

    @property
    def mid_price(self) -> Decimal | None:
        """Return the exact arithmetic midpoint, or ``None`` without both sides."""
        best_bid = self.best_bid
        best_ask = self.best_ask
        if best_bid is None or best_ask is None:
            return None
        return (best_bid + best_ask) / _TWO

    def __len__(self) -> int:
        """Return the number of active resting orders."""
        return self.order_count

    def __contains__(self, order_id: object) -> bool:
        """Return whether an active order identifier exists in the book."""
        return isinstance(order_id, str) and order_id in self._orders

    def get(self, order_id: str) -> Order | None:
        """Return an active order by identifier, or ``None`` when absent.

        Parameters
        ----------
        order_id
            Stable order identifier.

        Returns
        -------
        Order or None
            The immutable active order value.
        """
        return self._orders.get(order_id)

    def add(self, order: Order) -> None:
        """Add one non-marketable GTC limit order to the resting book.

        Parameters
        ----------
        order
            Valid limit order for this instrument with positive remaining quantity.

        Raises
        ------
        InvalidBookOrderError
            If the order is for another instrument, is non-resting, filled, off-grid,
            or otherwise unsuitable for the resting book.
        DuplicateOrderError
            If the identifier has appeared previously in this book's lifetime.
        DuplicateSequenceNumberError
            If the sequence number has appeared previously in this book's lifetime.
        CrossingOrderError
            If the order is marketable against the current opposite best quote.

        Determinism
        -----------
        Insertion position is derived from explicit price, time, and sequence fields;
        Python call order is not used as a hidden priority rule.
        """
        if not isinstance(order, Order):
            raise InvalidBookOrderError("order must be an Order")
        if order.order_id in self._seen_order_ids:
            raise DuplicateOrderError(f"order_id {order.order_id!r} has already been used")
        if order.sequence_number in self._seen_sequence_numbers:
            raise DuplicateSequenceNumberError(
                f"sequence_number {order.sequence_number} has already been used"
            )

        self._validate_resting_order(order)
        if self.would_cross(order):
            raise CrossingOrderError("marketable orders must be handled by the matching engine")

        price = cast(Decimal, order.price)
        price_ticks = self._instrument.price_to_ticks(price)
        side_levels = self._levels[order.side]
        level = side_levels.get(price_ticks)
        if level is None:
            level = []
            side_levels[price_ticks] = level
            insort(self._prices[order.side], price_ticks)

        priority = self._priority_key(order)
        priority_keys = [self._priority_key(self._orders[order_id]) for order_id in level]
        position = bisect_right(priority_keys, priority)
        level.insert(position, order.order_id)

        self._orders[order.order_id] = order
        self._seen_order_ids.add(order.order_id)
        self._seen_sequence_numbers.add(order.sequence_number)

    def cancel(self, order_id: str) -> Order:
        """Remove and return an active order.

        Parameters
        ----------
        order_id
            Identifier of the active order to cancel.

        Returns
        -------
        Order
            The immutable order state immediately before cancellation.

        Raises
        ------
        OrderNotFoundError
            If no active order has the supplied identifier.
        """
        order = self._require_order(order_id)
        self._remove(order)
        return order

    def apply_fill(self, order_id: str, quantity: Decimal) -> Order:
        """Reduce an active order by one exact executed quantity.

        Parameters
        ----------
        order_id
            Identifier of the resting order.
        quantity
            Positive lot-aligned executed quantity.

        Returns
        -------
        Order
            New immutable order state after the fill. A fully filled result is returned
            even though it is removed from the active book.

        Raises
        ------
        OrderNotFoundError
            If the order is not active.
        InvalidQuantityError
            If ``quantity`` is not positive, finite, Decimal, or lot-aligned.
        OverfillError
            If the fill exceeds the active remaining quantity.

        Determinism
        -----------
        Partial fills retain the original price-time priority. Full fills remove the
        order and its empty price level without reordering other orders.
        """
        order = self._require_order(order_id)
        self._instrument.validate_quantity(quantity)
        if quantity > order.remaining_quantity:
            raise OverfillError(
                f"fill quantity {quantity} exceeds remaining quantity "
                f"{order.remaining_quantity} for order {order_id!r}"
            )

        updated = order.with_remaining_quantity(order.remaining_quantity - quantity)
        if updated.is_filled:
            self._remove(order)
        else:
            self._orders[order_id] = updated
        return updated

    def best_order(self, side: Side) -> Order | None:
        """Return the highest-priority order on one side, or ``None`` when empty.

        Parameters
        ----------
        side
            Side whose best order is requested.

        Returns
        -------
        Order or None
            Best-priced and earliest-priority active order.

        Raises
        ------
        InvalidBookOrderError
            If ``side`` is not a :class:`Side`.
        """
        self._validate_side(side)
        prices = self._prices[side]
        if not prices:
            return None
        price_ticks = prices[-1] if side is Side.BUY else prices[0]
        order_id = self._levels[side][price_ticks][0]
        return self._orders[order_id]

    def orders_at(self, side: Side, price: Decimal) -> tuple[Order, ...]:
        """Return active orders at a price in time-sequence priority order.

        Parameters
        ----------
        side
            Book side to inspect.
        price
            Positive tick-aligned price.

        Returns
        -------
        tuple[Order, ...]
            Immutable ordered view; empty when the level does not exist.
        """
        self._validate_side(side)
        price_ticks = self._instrument.price_to_ticks(price)
        order_ids = self._levels[side].get(price_ticks, [])
        return tuple(self._orders[order_id] for order_id in order_ids)

    def orders_by_priority(self, side: Side) -> tuple[Order, ...]:
        """Return all active orders on one side in price-time priority order.

        Parameters
        ----------
        side
            Side to inspect.

        Returns
        -------
        tuple[Order, ...]
            Bids from highest to lowest price and asks from lowest to highest price,
            with time-sequence priority inside each level.
        """
        self._validate_side(side)
        ordered: list[Order] = []
        for price_ticks in self._iter_price_ticks(side):
            ordered.extend(self._orders[order_id] for order_id in self._levels[side][price_ticks])
        return tuple(ordered)

    def would_cross(self, order: Order) -> bool:
        """Return whether an incoming order is marketable against this book.

        Parameters
        ----------
        order
            Incoming market or limit order for this instrument.

        Returns
        -------
        bool
            ``True`` when at least one opposite resting order is executable under the
            incoming order's price constraint.

        Raises
        ------
        InvalidBookOrderError
            If ``order`` is not an Order or targets another instrument.
        InvalidPriceError
            If a limit price is off the instrument tick grid.
        """
        if not isinstance(order, Order):
            raise InvalidBookOrderError("order must be an Order")
        if order.instrument_id != self._instrument.instrument_id:
            raise InvalidBookOrderError(
                f"order instrument {order.instrument_id!r} does not match book instrument "
                f"{self._instrument.instrument_id!r}"
            )

        opposite_best = self.best_ask if order.side is Side.BUY else self.best_bid
        if opposite_best is None:
            return False
        if order.order_type is OrderType.MARKET:
            return True

        price = cast(Decimal, order.price)
        self._instrument.validate_price(price)
        if order.side is Side.BUY:
            return price >= opposite_best
        return price <= opposite_best

    def depth(self, side: Side, *, levels: int | None = None) -> tuple[DepthLevel, ...]:
        """Return aggregated depth levels in best-to-worst order.

        Parameters
        ----------
        side
            Book side to aggregate.
        levels
            Optional positive maximum number of levels.

        Returns
        -------
        tuple[DepthLevel, ...]
            Immutable aggregate levels.

        Raises
        ------
        InvalidDepthError
            If ``levels`` is not ``None`` or a positive integer.
        """
        self._validate_side(side)
        limit = self._validate_levels(levels)
        result: list[DepthLevel] = []
        for price_ticks in self._iter_price_ticks(side):
            order_ids = self._levels[side][price_ticks]
            total_quantity = sum(
                (self._orders[order_id].remaining_quantity for order_id in order_ids),
                start=_ZERO,
            )
            result.append(
                DepthLevel(
                    side=side,
                    price=self._instrument.ticks_to_price(price_ticks),
                    price_ticks=price_ticks,
                    total_quantity=total_quantity,
                    order_count=len(order_ids),
                )
            )
            if limit is not None and len(result) >= limit:
                break
        return tuple(result)

    def depth_imbalance(self, *, levels: int | None = None) -> Decimal | None:
        """Return aggregate depth imbalance for symmetric depth limits.

        The measure is ``(bid_quantity - ask_quantity) / total_quantity``.

        Parameters
        ----------
        levels
            Optional positive maximum number of levels from each side.

        Returns
        -------
        Decimal or None
            Exact value in ``[-1, 1]``. ``None`` denotes no visible quantity on either
            side and is intentionally distinct from a balanced value of zero.
        """
        bids = self.depth(Side.BUY, levels=levels)
        asks = self.depth(Side.SELL, levels=levels)
        bid_quantity = sum((level.total_quantity for level in bids), start=_ZERO)
        ask_quantity = sum((level.total_quantity for level in asks), start=_ZERO)
        total_quantity = bid_quantity + ask_quantity
        if total_quantity == _ZERO:
            return None
        return (bid_quantity - ask_quantity) / total_quantity

    def snapshot(self, *, levels: int | None = None) -> OrderBookSnapshot:
        """Return an immutable aggregate snapshot of the current book.

        Parameters
        ----------
        levels
            Optional positive maximum number of levels retained on each side.

        Returns
        -------
        OrderBookSnapshot
            Deterministic quote, depth, and imbalance view.
        """
        bids = self.depth(Side.BUY, levels=levels)
        asks = self.depth(Side.SELL, levels=levels)
        return OrderBookSnapshot(
            instrument_id=self._instrument.instrument_id,
            bids=bids,
            asks=asks,
            best_bid=self.best_bid,
            best_ask=self.best_ask,
            spread=self.spread,
            mid_price=self.mid_price,
            imbalance=self.depth_imbalance(levels=levels),
            order_count=self.order_count,
        )

    def validate_invariants(self) -> None:
        """Raise when internal indexes disagree with active order state.

        Raises
        ------
        OrderBookInvariantError
            If price indexes, levels, active orders, or priority ordering are
            inconsistent.

        Notes
        -----
        This method is intended for tests, validation runs, and defensive diagnostics.
        It is not called automatically after every mutation because it is linear in the
        number of active orders.
        """
        indexed_order_ids: list[str] = []
        for side in Side:
            prices = self._prices[side]
            if prices != sorted(set(prices)):
                raise OrderBookInvariantError(f"{side.value} price index is not sorted and unique")
            if set(prices) != set(self._levels[side]):
                raise OrderBookInvariantError(f"{side.value} price index and levels disagree")

            for price_ticks in prices:
                order_ids = self._levels[side][price_ticks]
                if not order_ids:
                    raise OrderBookInvariantError("empty price levels must not be retained")
                orders = [self._orders.get(order_id) for order_id in order_ids]
                if any(order is None for order in orders):
                    raise OrderBookInvariantError("price level references a missing order")
                concrete_orders = [order for order in orders if order is not None]
                priorities = [self._priority_key(order) for order in concrete_orders]
                if priorities != sorted(priorities):
                    raise OrderBookInvariantError("orders within a price level are misordered")
                for order in concrete_orders:
                    price = order.price
                    if price is None:
                        raise OrderBookInvariantError("resting order has no limit price")
                    if order.side is not side:
                        raise OrderBookInvariantError("order is indexed on the wrong side")
                    if self._instrument.price_to_ticks(price) != price_ticks:
                        raise OrderBookInvariantError("order is indexed at the wrong price")
                    if order.is_filled:
                        raise OrderBookInvariantError("filled order remains active")
                indexed_order_ids.extend(order_ids)

        if len(indexed_order_ids) != len(set(indexed_order_ids)):
            raise OrderBookInvariantError("an active order is indexed more than once")
        if set(indexed_order_ids) != set(self._orders):
            raise OrderBookInvariantError("active order map and price levels disagree")

        best_bid = self.best_bid
        best_ask = self.best_ask
        if best_bid is not None and best_ask is not None and best_bid >= best_ask:
            raise OrderBookInvariantError("resting book is crossed or locked")

    def _validate_resting_order(self, order: Order) -> None:
        if order.instrument_id != self._instrument.instrument_id:
            raise InvalidBookOrderError(
                f"order instrument {order.instrument_id!r} does not match book instrument "
                f"{self._instrument.instrument_id!r}"
            )
        if order.order_type is not OrderType.LIMIT:
            raise InvalidBookOrderError("only limit orders may rest in the order book")
        if order.time_in_force is not TimeInForce.GOOD_TIL_CANCELLED:
            raise InvalidBookOrderError("only good-til-cancelled orders may rest in the order book")
        if order.is_filled:
            raise InvalidBookOrderError("filled orders cannot rest in the order book")

        price = cast(Decimal, order.price)
        self._instrument.validate_price(price)
        self._instrument.validate_quantity(order.quantity)
        self._instrument.validate_quantity(order.remaining_quantity)

    @staticmethod
    def _priority_key(order: Order) -> tuple[int | float, int]:
        return (order.submitted_at, order.sequence_number)

    @staticmethod
    def _validate_side(side: Side) -> None:
        if not isinstance(side, Side):
            raise InvalidBookOrderError("side must be a Side")

    @staticmethod
    def _validate_levels(levels: int | None) -> int | None:
        if levels is None:
            return None
        if isinstance(levels, bool) or not isinstance(levels, int) or levels <= 0:
            raise InvalidDepthError("levels must be a positive integer or None")
        return levels

    def _iter_price_ticks(self, side: Side) -> tuple[int, ...]:
        prices = self._prices[side]
        if side is Side.BUY:
            return tuple(reversed(prices))
        return tuple(prices)

    def _require_order(self, order_id: str) -> Order:
        if not isinstance(order_id, str) or not order_id.strip():
            raise OrderNotFoundError("order_id must identify an active order")
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(f"active order {order_id!r} was not found")
        return order

    def _remove(self, order: Order) -> None:
        price = cast(Decimal, order.price)
        price_ticks = self._instrument.price_to_ticks(price)
        level = self._levels[order.side][price_ticks]
        level.remove(order.order_id)
        del self._orders[order.order_id]

        if not level:
            del self._levels[order.side][price_ticks]
            prices = self._prices[order.side]
            position = bisect_left(prices, price_ticks)
            if position >= len(prices) or prices[position] != price_ticks:
                raise OrderBookInvariantError("price index lost an active level")
            prices.pop(position)
