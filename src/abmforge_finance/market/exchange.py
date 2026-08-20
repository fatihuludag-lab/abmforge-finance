"""Atomic single-instrument exchange orchestration."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from abmforge_finance.domain import Account, Instrument, Order, Portfolio, Side, Trade
from abmforge_finance.exceptions import (
    ExchangeInvariantError,
    InsufficientAvailableInventoryError,
    InsufficientBuyingPowerError,
    InsufficientCashError,
    InsufficientInventoryError,
    InvalidIncomingOrderError,
    OrderOwnershipError,
)
from abmforge_finance.market.clearing import ClearingEngine, SettlementResult
from abmforge_finance.market.matching_engine import MatchingEngine, MatchResult
from abmforge_finance.market.order_book import OrderBookSnapshot

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class ExchangeResult:
    """Immutable result of one successfully committed exchange submission."""

    match_result: MatchResult
    settlements: tuple[SettlementResult, ...]

    @property
    def final_order(self) -> Order:
        """Return the incoming order state after matching."""
        return self.match_result.final_order

    @property
    def trades(self) -> tuple[Trade, ...]:
        """Return committed trades in deterministic execution order."""
        return self.match_result.trades

    @property
    def rested(self) -> bool:
        """Return whether a positive GTC residual rests after the transaction."""
        return self.match_result.rested

    @property
    def executed_quantity(self) -> Decimal:
        """Return the exact quantity executed from the incoming order."""
        return self.match_result.executed_quantity

    @property
    def cancelled_quantity(self) -> Decimal:
        """Return the exact IOC residual cancelled by matching."""
        return self.match_result.cancelled_quantity


class Exchange:
    """Compose matching and clearing into one atomic in-memory market transaction.

    The Phase 5 baseline owns one :class:`MatchingEngine` and one
    :class:`ClearingEngine`. Order submission is staged on independent copies of both
    components. The staged state becomes visible only after matching, settlement, and
    resting-order resource commitments all validate successfully.

    Resting buy orders reserve economic capacity conservatively at their limit price.
    Resting sell orders reserve their remaining quantity when short selling is
    disabled. The reservation ledger is derived from the deterministic resting book
    rather than stored separately, avoiding a second mutable source of truth.

    Notes
    -----
    Matching currently emits zero fees. A future fee model that can charge future
    resting executions must extend the buying-power commitment formula before such
    fees are enabled in end-to-end exchange experiments.
    """

    __slots__ = ("_clearing", "_matching")

    def __init__(self, instrument: Instrument, *, allow_short_selling: bool = False) -> None:
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not isinstance(allow_short_selling, bool):
            raise TypeError("allow_short_selling must be a bool")
        self._matching = MatchingEngine(instrument)
        self._clearing = ClearingEngine(allow_short_selling=allow_short_selling)

    @property
    def instrument(self) -> Instrument:
        """Return the immutable instrument traded by this exchange."""
        return self._matching.instrument

    @property
    def allow_short_selling(self) -> bool:
        """Return whether negative post-trade inventory is permitted."""
        return self._clearing.allow_short_selling

    @property
    def fee_balance(self) -> Decimal:
        """Return the current signed venue fee balance."""
        return self._clearing.fee_balance

    @property
    def next_trade_sequence(self) -> int:
        """Return the deterministic sequence assigned to the next execution."""
        return self._matching.next_trade_sequence

    @property
    def next_submission_sequence(self) -> int:
        """Return the minimum valid sequence for the next accepted order submission."""
        return self._matching.next_submission_sequence

    @property
    def last_submitted_at(self) -> int | float | None:
        """Return the timestamp of the last accepted order submission, if any."""
        return self._matching.last_submitted_at

    @property
    def settled_trade_ids(self) -> tuple[str, ...]:
        """Return successfully settled trade identifiers in settlement order."""
        return self._clearing.settled_trade_ids

    def register(self, account: Account, portfolio: Portfolio | None = None) -> None:
        """Register one participant's initial cash and inventory state."""
        self._clearing.register(account, portfolio)

    def account(self, participant_id: str) -> Account:
        """Return a participant's current immutable cash account."""
        return self._clearing.account(participant_id)

    def portfolio(self, participant_id: str) -> Portfolio:
        """Return a participant's current immutable portfolio."""
        return self._clearing.portfolio(participant_id)

    def order(self, order_id: str) -> Order | None:
        """Return an active resting order without exposing mutable book internals."""
        return self._matching.book.get(order_id)

    def snapshot(self, *, levels: int | None = None) -> OrderBookSnapshot:
        """Return an immutable order-book snapshot."""
        return self._matching.book.snapshot(levels=levels)

    def cancel(self, order_id: str, *, participant_id: str) -> Order:
        """Cancel one active resting order owned by ``participant_id``.

        Cancellation only reduces outstanding resource commitments, so it does not
        require a clearing transaction. Submission sequence numbers remain consumed;
        cancelled order identifiers cannot be reused by the matching engine.
        """
        self._clearing.account(participant_id)
        order = self._matching.book.get(order_id)
        if order is None:
            return self._matching.book.cancel(order_id)
        if order.agent_id != participant_id:
            raise OrderOwnershipError(
                f"order_id {order_id!r} is owned by participant_id {order.agent_id!r}"
            )
        return self._matching.book.cancel(order_id)

    def submit(self, order: Order) -> ExchangeResult:
        """Atomically match, settle, risk-check, and commit one incoming order.

        Expected validation, matching, settlement, or resource-commitment failures
        leave the visible exchange state unchanged because all work is performed on
        staged component copies before commit.
        """
        if not isinstance(order, Order):
            raise InvalidIncomingOrderError("order must be an Order")

        # Every order, including an IOC order that ultimately executes nothing, must
        # belong to a registered exchange participant.
        self._clearing.account(order.agent_id)
        self._clearing.portfolio(order.agent_id)

        staged_matching = deepcopy(self._matching)
        staged_clearing = deepcopy(self._clearing)

        match_result = staged_matching.submit(order)
        try:
            settlements = tuple(staged_clearing.settle(trade) for trade in match_result.trades)
        except InsufficientCashError as exc:
            raise InsufficientBuyingPowerError(
                f"participant cash cannot settle order_id {order.order_id!r}"
            ) from exc
        except InsufficientInventoryError as exc:
            raise InsufficientAvailableInventoryError(
                f"participant inventory cannot settle order_id {order.order_id!r}"
            ) from exc

        self._validate_resting_commitments(staged_matching, staged_clearing)

        if tuple(result.trade_id for result in settlements) != tuple(
            trade.trade_id for trade in match_result.trades
        ):
            raise ExchangeInvariantError("settlement results do not correspond to matched trades")

        self._matching = staged_matching
        self._clearing = staged_clearing
        return ExchangeResult(match_result=match_result, settlements=settlements)

    def _validate_resting_commitments(
        self,
        matching: MatchingEngine,
        clearing: ClearingEngine,
    ) -> None:
        cash_commitments: dict[str, Decimal] = {}
        inventory_commitments: dict[str, Decimal] = {}

        for order in matching.book.orders_by_priority(Side.BUY):
            price = cast(Decimal, order.price)
            cash_commitments[order.agent_id] = cash_commitments.get(order.agent_id, _ZERO) + (
                price * order.remaining_quantity
            )

        for order in matching.book.orders_by_priority(Side.SELL):
            inventory_commitments[order.agent_id] = (
                inventory_commitments.get(order.agent_id, _ZERO) + order.remaining_quantity
            )

        for participant_id in sorted(cash_commitments):
            committed = cash_commitments[participant_id]
            available = clearing.account(participant_id).cash
            if available < committed:
                raise InsufficientBuyingPowerError(
                    f"participant_id {participant_id!r} has cash {available} but resting "
                    f"buy commitments require {committed}"
                )

        if clearing.allow_short_selling:
            return

        for participant_id in sorted(inventory_commitments):
            committed = inventory_commitments[participant_id]
            available = clearing.portfolio(participant_id).quantity(self.instrument.instrument_id)
            if available < committed:
                raise InsufficientAvailableInventoryError(
                    f"participant_id {participant_id!r} has inventory {available} but resting "
                    f"sell commitments require {committed}"
                )
