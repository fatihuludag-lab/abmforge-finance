"""Atomic deterministic cash-and-inventory settlement for executed trades."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain import Account, Portfolio, Trade
from abmforge_finance.exceptions import (
    DuplicateParticipantError,
    DuplicateSettlementError,
    InsufficientCashError,
    InsufficientInventoryError,
    InvalidClearingRegistrationError,
    OutOfOrderSettlementError,
    SettlementInvariantError,
    UnknownParticipantError,
)

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SettlementResult:
    """Immutable audit record for one successfully settled trade."""

    trade_id: str
    buyer_id: str
    seller_id: str
    instrument_id: str
    notional: Decimal
    buyer_cash_delta: Decimal
    seller_cash_delta: Decimal
    buyer_inventory_delta: Decimal
    seller_inventory_delta: Decimal
    fee_delta: Decimal

    @property
    def participant_cash_delta(self) -> Decimal:
        """Return the net cash delta across buyer and seller roles."""
        return self.buyer_cash_delta + self.seller_cash_delta

    @property
    def inventory_delta(self) -> Decimal:
        """Return the net instrument-unit delta across buyer and seller roles."""
        return self.buyer_inventory_delta + self.seller_inventory_delta


class ClearingEngine:
    """Settle immutable :class:`Trade` values into participant ledgers.

    The baseline policy disallows negative participant cash and, by default,
    disallows negative inventory. ``allow_short_selling=True`` relaxes only the
    inventory constraint. Each accepted trade identifier can settle exactly once.

    Notes
    -----
    This engine is atomic with respect to its own account/portfolio state, but Phase
    4 does not yet make matching and clearing one transaction. The future exchange
    orchestrator must perform pre-trade admissibility checks before submitting an
    order whose resulting trade could fail settlement.
    """

    __slots__ = (
        "_accounts",
        "_allow_short_selling",
        "_fee_balance",
        "_last_executed_at",
        "_last_sequence_number",
        "_portfolios",
        "_settled_trade_ids",
        "_settlement_order",
    )

    def __init__(self, *, allow_short_selling: bool = False) -> None:
        if not isinstance(allow_short_selling, bool):
            raise TypeError("allow_short_selling must be a bool")
        self._allow_short_selling = allow_short_selling
        self._accounts: dict[str, Account] = {}
        self._portfolios: dict[str, Portfolio] = {}
        self._settled_trade_ids: set[str] = set()
        self._settlement_order: list[str] = []
        self._fee_balance = _ZERO
        self._last_executed_at: int | float | None = None
        self._last_sequence_number: int | None = None

    @property
    def allow_short_selling(self) -> bool:
        """Return whether negative post-settlement positions are allowed."""
        return self._allow_short_selling

    @property
    def fee_balance(self) -> Decimal:
        """Return accumulated signed venue fees; negative values denote net rebates."""
        return self._fee_balance

    @property
    def settled_trade_ids(self) -> tuple[str, ...]:
        """Return settled trade identifiers in accepted settlement order."""
        return tuple(self._settlement_order)

    def register(self, account: Account, portfolio: Portfolio | None = None) -> None:
        """Register one participant's initial cash and inventory state."""
        if not isinstance(account, Account):
            raise InvalidClearingRegistrationError("account must be an Account")
        if account.participant_id in self._accounts:
            raise DuplicateParticipantError(
                f"participant_id {account.participant_id!r} is already registered"
            )
        if account.cash < _ZERO:
            raise InvalidClearingRegistrationError(
                "baseline clearing requires non-negative registered cash"
            )

        resolved_portfolio = portfolio or Portfolio(account.participant_id)
        if not isinstance(resolved_portfolio, Portfolio):
            raise InvalidClearingRegistrationError("portfolio must be a Portfolio or None")
        if resolved_portfolio.participant_id != account.participant_id:
            raise InvalidClearingRegistrationError(
                "account and portfolio participant_id values must match"
            )
        if not self._allow_short_selling and any(
            quantity < _ZERO for _, quantity in resolved_portfolio.positions
        ):
            raise InvalidClearingRegistrationError(
                "negative registered inventory requires allow_short_selling=True"
            )

        self._accounts[account.participant_id] = account
        self._portfolios[account.participant_id] = resolved_portfolio

    def account(self, participant_id: str) -> Account:
        """Return the current immutable cash account for a registered participant."""
        try:
            return self._accounts[participant_id]
        except (KeyError, TypeError) as exc:
            raise UnknownParticipantError(
                f"participant_id {participant_id!r} is not registered"
            ) from exc

    def portfolio(self, participant_id: str) -> Portfolio:
        """Return the current immutable portfolio for a registered participant."""
        try:
            return self._portfolios[participant_id]
        except (KeyError, TypeError) as exc:
            raise UnknownParticipantError(
                f"participant_id {participant_id!r} is not registered"
            ) from exc

    def settle(self, trade: Trade) -> SettlementResult:
        """Atomically settle one executed trade exactly once."""
        if not isinstance(trade, Trade):
            raise TypeError("trade must be a Trade")
        if trade.trade_id in self._settled_trade_ids:
            raise DuplicateSettlementError(f"trade_id {trade.trade_id!r} is already settled")
        if self._last_executed_at is not None and trade.executed_at < self._last_executed_at:
            raise OutOfOrderSettlementError("executed_at cannot move backwards")
        if (
            self._last_sequence_number is not None
            and trade.sequence_number <= self._last_sequence_number
        ):
            raise OutOfOrderSettlementError(
                "sequence_number must increase strictly across settlements"
            )

        participant_ids = {trade.buyer_id, trade.seller_id}
        ordered_participant_ids = tuple(sorted(participant_ids))
        unknown = sorted(participant_ids.difference(self._accounts))
        if unknown:
            raise UnknownParticipantError(f"unregistered participant(s): {', '.join(unknown)}")

        cash_deltas = {participant_id: _ZERO for participant_id in ordered_participant_ids}
        inventory_deltas = {participant_id: _ZERO for participant_id in ordered_participant_ids}

        buyer_cash_delta = -(trade.notional + trade.buyer_fee)
        seller_cash_delta = trade.notional - trade.seller_fee
        cash_deltas[trade.buyer_id] += buyer_cash_delta
        cash_deltas[trade.seller_id] += seller_cash_delta
        inventory_deltas[trade.buyer_id] += trade.quantity
        inventory_deltas[trade.seller_id] -= trade.quantity

        if sum(cash_deltas.values(), _ZERO) + trade.total_fees != _ZERO:
            raise SettlementInvariantError("cash deltas and venue fees do not conserve cash")
        if sum(inventory_deltas.values(), _ZERO) != _ZERO:
            raise SettlementInvariantError("inventory deltas do not conserve instrument units")

        next_accounts: dict[str, Account] = {}
        next_portfolios: dict[str, Portfolio] = {}
        for participant_id in ordered_participant_ids:
            next_account = self._accounts[participant_id].with_cash_delta(
                cash_deltas[participant_id]
            )
            if next_account.cash < _ZERO:
                raise InsufficientCashError(
                    f"participant_id {participant_id!r} would have negative cash"
                )
            next_portfolio = self._portfolios[participant_id].with_quantity_delta(
                trade.instrument_id,
                inventory_deltas[participant_id],
            )
            if (
                not self._allow_short_selling
                and next_portfolio.quantity(trade.instrument_id) < _ZERO
            ):
                raise InsufficientInventoryError(
                    f"participant_id {participant_id!r} would have negative inventory"
                )
            next_accounts[participant_id] = next_account
            next_portfolios[participant_id] = next_portfolio

        self._accounts.update(next_accounts)
        self._portfolios.update(next_portfolios)
        self._fee_balance += trade.total_fees
        self._settled_trade_ids.add(trade.trade_id)
        self._settlement_order.append(trade.trade_id)
        self._last_executed_at = trade.executed_at
        self._last_sequence_number = trade.sequence_number

        return SettlementResult(
            trade_id=trade.trade_id,
            buyer_id=trade.buyer_id,
            seller_id=trade.seller_id,
            instrument_id=trade.instrument_id,
            notional=trade.notional,
            buyer_cash_delta=buyer_cash_delta,
            seller_cash_delta=seller_cash_delta,
            buyer_inventory_delta=trade.quantity,
            seller_inventory_delta=-trade.quantity,
            fee_delta=trade.total_fees,
        )
