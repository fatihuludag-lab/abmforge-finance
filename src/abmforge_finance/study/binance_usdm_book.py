"""Deterministic Binance USD-M local order-book synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.binance_usdm_contract import (
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMBookLevel,
    BinanceUsdMDepthSnapshot,
    BinanceUsdMDepthUpdateEvent,
)

_ZERO = Decimal("0")
_TWO = Decimal("2")


class BinanceUsdMBookSynchronizationError(InvalidMetricInputError):
    """Raised when the local Binance depth book cannot remain valid."""


@dataclass(frozen=True, slots=True)
class BinanceUsdMLocalBookState:
    """Immutable snapshot of one synchronized local book."""

    symbol: str
    last_update_id: int
    event_time_ms: int
    transaction_time_ms: int
    bids: tuple[BinanceUsdMBookLevel, ...]
    asks: tuple[BinanceUsdMBookLevel, ...]

    def __post_init__(self) -> None:
        if not self.bids:
            raise BinanceUsdMBookSynchronizationError(
                "synchronized book must contain at least one bid"
            )

        if not self.asks:
            raise BinanceUsdMBookSynchronizationError(
                "synchronized book must contain at least one ask"
            )

        if any(
            self.bids[index].price <= self.bids[index + 1].price
            for index in range(len(self.bids) - 1)
        ):
            raise BinanceUsdMBookSynchronizationError("book bids must be strictly descending")

        if any(
            self.asks[index].price >= self.asks[index + 1].price
            for index in range(len(self.asks) - 1)
        ):
            raise BinanceUsdMBookSynchronizationError("book asks must be strictly ascending")

        if self.best_bid >= self.best_ask:
            raise BinanceUsdMBookSynchronizationError(
                "synchronized book must have a positive spread"
            )

    @property
    def best_bid(self) -> Decimal:
        """Return best bid price."""

        return self.bids[0].price

    @property
    def best_ask(self) -> Decimal:
        """Return best ask price."""

        return self.asks[0].price

    @property
    def midpoint(self) -> Decimal:
        """Return best-bid/best-ask midpoint."""

        return (self.best_bid + self.best_ask) / _TWO

    @property
    def bid_depth(self) -> Decimal:
        """Return maintained displayed bid quantity."""

        return sum(
            (level.quantity for level in self.bids),
            start=_ZERO,
        )

    @property
    def ask_depth(self) -> Decimal:
        """Return maintained displayed ask quantity."""

        return sum(
            (level.quantity for level in self.asks),
            start=_ZERO,
        )

    @property
    def thin_side_depth(self) -> Decimal:
        """Return minimum maintained displayed side depth."""

        return min(self.bid_depth, self.ask_depth)


class BinanceUsdMLocalBook:
    """Mutable deterministic reconstruction of one synchronized book."""

    __slots__ = (
        "_asks",
        "_bids",
        "_contract",
        "_event_time_ms",
        "_last_update_id",
        "_symbol",
        "_synchronized",
        "_transaction_time_ms",
    )

    def __init__(
        self,
        *,
        contract: BinanceUsdMEmpiricalContract,
    ) -> None:
        self._contract = contract
        self._symbol = contract.symbol
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._last_update_id = -1
        self._event_time_ms = 0
        self._transaction_time_ms = 0
        self._synchronized = False

    @classmethod
    def synchronize(
        cls,
        snapshot: BinanceUsdMDepthSnapshot,
        buffered_events: tuple[BinanceUsdMDepthUpdateEvent, ...],
        *,
        contract: BinanceUsdMEmpiricalContract | None = None,
    ) -> BinanceUsdMLocalBook:
        """Initialize a local book using the official snapshot bridge."""

        active_contract = binance_usdm_empirical_contract() if contract is None else contract

        if not isinstance(
            snapshot,
            BinanceUsdMDepthSnapshot,
        ):
            raise TypeError("snapshot must be a BinanceUsdMDepthSnapshot")

        if not isinstance(buffered_events, tuple):
            raise TypeError("buffered_events must be a tuple")

        for index, event in enumerate(buffered_events):
            if not isinstance(
                event,
                BinanceUsdMDepthUpdateEvent,
            ):
                raise TypeError(f"buffered_events[{index}] must be a BinanceUsdMDepthUpdateEvent")

        if snapshot.symbol != active_contract.symbol:
            raise BinanceUsdMBookSynchronizationError(
                "snapshot symbol does not match the frozen contract"
            )

        book = cls(contract=active_contract)
        book._seed(snapshot)

        retained = tuple(
            event for event in buffered_events if event.final_update_id >= snapshot.last_update_id
        )

        if not retained:
            raise BinanceUsdMBookSynchronizationError(
                "buffer does not contain a snapshot bridge event"
            )

        first = retained[0]
        book._validate_event_identity(first)

        if not (first.first_update_id <= snapshot.last_update_id <= first.final_update_id):
            raise BinanceUsdMBookSynchronizationError(
                "first retained depth event does not bridge snapshot lastUpdateId"
            )

        book._apply_levels(first)
        book._last_update_id = first.final_update_id
        book._event_time_ms = first.event_time_ms
        book._transaction_time_ms = first.transaction_time_ms
        book._synchronized = True
        book._validate_integrity()

        for event in retained[1:]:
            book.apply(event)

        return book

    @property
    def is_synchronized(self) -> bool:
        """Return whether the book passed snapshot synchronization."""

        return self._synchronized

    @property
    def last_update_id(self) -> int:
        """Return final update id applied to the local book."""

        if not self._synchronized:
            raise BinanceUsdMBookSynchronizationError("local book is not synchronized")

        return self._last_update_id

    def apply(
        self,
        event: BinanceUsdMDepthUpdateEvent,
    ) -> None:
        """Apply one subsequent contiguous absolute depth update."""

        if not self._synchronized:
            raise BinanceUsdMBookSynchronizationError("local book is not synchronized")

        if not isinstance(
            event,
            BinanceUsdMDepthUpdateEvent,
        ):
            raise TypeError("event must be a BinanceUsdMDepthUpdateEvent")

        self._validate_event_identity(event)

        if event.previous_final_update_id != self._last_update_id:
            raise BinanceUsdMBookSynchronizationError(
                "depth update continuity failure: pu must equal previous u"
            )

        if event.final_update_id <= self._last_update_id:
            raise BinanceUsdMBookSynchronizationError("depth update ids must advance monotonically")

        self._apply_levels(event)

        self._last_update_id = event.final_update_id
        self._event_time_ms = event.event_time_ms
        self._transaction_time_ms = event.transaction_time_ms

        self._validate_integrity()

    def state(self) -> BinanceUsdMLocalBookState:
        """Return an immutable deterministic state snapshot."""

        if not self._synchronized:
            raise BinanceUsdMBookSynchronizationError("local book is not synchronized")

        bids = tuple(
            BinanceUsdMBookLevel(price, quantity)
            for price, quantity in sorted(
                self._bids.items(),
                reverse=True,
            )
        )

        asks = tuple(
            BinanceUsdMBookLevel(price, quantity) for price, quantity in sorted(self._asks.items())
        )

        return BinanceUsdMLocalBookState(
            symbol=self._symbol,
            last_update_id=self._last_update_id,
            event_time_ms=self._event_time_ms,
            transaction_time_ms=(self._transaction_time_ms),
            bids=bids,
            asks=asks,
        )

    def _seed(
        self,
        snapshot: BinanceUsdMDepthSnapshot,
    ) -> None:
        self._bids = {level.price: level.quantity for level in snapshot.bids}
        self._asks = {level.price: level.quantity for level in snapshot.asks}

        if len(self._bids) != len(snapshot.bids):
            raise BinanceUsdMBookSynchronizationError("snapshot contains duplicate bid prices")

        if len(self._asks) != len(snapshot.asks):
            raise BinanceUsdMBookSynchronizationError("snapshot contains duplicate ask prices")

    def _validate_event_identity(
        self,
        event: BinanceUsdMDepthUpdateEvent,
    ) -> None:
        if event.symbol != self._contract.symbol:
            raise BinanceUsdMBookSynchronizationError("depth event symbol does not match contract")

        if event.pair != self._contract.pair:
            raise BinanceUsdMBookSynchronizationError("depth event pair does not match contract")

        if event.symbol_type != self._contract.required_symbol_type:
            raise BinanceUsdMBookSynchronizationError(
                "depth event symbol type does not match contract"
            )

    @staticmethod
    def _apply_side(
        side: dict[Decimal, Decimal],
        updates: tuple[BinanceUsdMBookLevel, ...],
    ) -> None:
        for level in updates:
            if level.quantity == _ZERO:
                side.pop(level.price, None)
            else:
                side[level.price] = level.quantity

    def _apply_levels(
        self,
        event: BinanceUsdMDepthUpdateEvent,
    ) -> None:
        self._apply_side(
            self._bids,
            event.bid_updates,
        )
        self._apply_side(
            self._asks,
            event.ask_updates,
        )

    def _validate_integrity(self) -> None:
        if not self._bids:
            raise BinanceUsdMBookSynchronizationError("synchronized local book lost all bid levels")

        if not self._asks:
            raise BinanceUsdMBookSynchronizationError("synchronized local book lost all ask levels")

        if max(self._bids) >= min(self._asks):
            raise BinanceUsdMBookSynchronizationError(
                "synchronized local book became crossed or locked"
            )
