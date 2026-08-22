"""Framework-independent finance research recorder."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.agents import Trader
from abmforge_finance.domain import Order, Trade, TradingDecision
from abmforge_finance.exceptions import RecordingStateError
from abmforge_finance.market import Exchange, ExchangeResult, OrderBookSnapshot
from abmforge_finance.recording.dataset import FinanceResearchDataset
from abmforge_finance.recording.schema import (
    AccountRecord,
    CancellationRecord,
    DecisionRecord,
    MarketStateRecord,
    OrderRecord,
    ParticipantRecord,
    PositionRecord,
    RecordingPhase,
    TradeRecord,
)

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class FinanceRecordingConfig:
    """Select finance-specific tables without changing market behavior."""

    record_decisions: bool = True
    record_orders: bool = True
    record_trades: bool = True
    record_market_states: bool = True
    record_accounts: bool = True
    record_positions: bool = True
    record_cancellations: bool = True


class FinanceResearchRecorder:
    """Capture exact finance state without importing ABMForge or mutating the market."""

    __slots__ = (
        "_accounts",
        "_cancellations",
        "_decisions",
        "_market_states",
        "_orders",
        "_participant_ids",
        "_participants",
        "_positions",
        "_started",
        "_trades",
        "config",
    )

    def __init__(self, config: FinanceRecordingConfig | None = None) -> None:
        self.config = FinanceRecordingConfig() if config is None else config
        if not isinstance(self.config, FinanceRecordingConfig):
            raise TypeError("config must be a FinanceRecordingConfig")
        self._started = False
        self._participant_ids: tuple[str, ...] = ()
        self._participants: list[ParticipantRecord] = []
        self._decisions: list[DecisionRecord] = []
        self._cancellations: list[CancellationRecord] = []
        self._orders: list[OrderRecord] = []
        self._trades: list[TradeRecord] = []
        self._market_states: list[MarketStateRecord] = []
        self._accounts: list[AccountRecord] = []
        self._positions: list[PositionRecord] = []

    @property
    def started(self) -> bool:
        """Return whether the recorder has captured its initial state."""

        return self._started

    @property
    def dataset(self) -> FinanceResearchDataset:
        """Return a validated immutable snapshot of every recorded table."""

        dataset = FinanceResearchDataset(
            participants=tuple(self._participants),
            decisions=tuple(self._decisions),
            cancellations=tuple(self._cancellations),
            orders=tuple(self._orders),
            trades=tuple(self._trades),
            market_states=tuple(self._market_states),
            accounts=tuple(self._accounts),
            positions=tuple(self._positions),
        )
        dataset.validate()
        return dataset

    def start(self, exchange: Exchange, traders: tuple[Trader, ...]) -> None:
        """Freeze participant metadata and optional initial balance tables."""

        if self._started:
            raise RecordingStateError("finance research recorder may only start once")
        if not isinstance(exchange, Exchange):
            raise TypeError("exchange must be an Exchange")
        if not isinstance(traders, tuple) or not all(
            isinstance(trader, Trader) for trader in traders
        ):
            raise TypeError("traders must be a tuple of Trader values")

        ordered = tuple(sorted(traders, key=lambda trader: trader.agent_id))
        ids = tuple(trader.agent_id for trader in ordered)
        if len(set(ids)) != len(ids):
            raise RecordingStateError("recorded trader agent_id values must be unique")

        instrument_id = exchange.instrument.instrument_id
        for trader in ordered:
            policy_type = f"{type(trader.policy).__module__}.{type(trader.policy).__qualname__}"
            account = exchange.account(trader.agent_id)
            inventory = exchange.portfolio(trader.agent_id).quantity(instrument_id)
            self._participants.append(
                ParticipantRecord(
                    agent_id=trader.agent_id,
                    policy_type=policy_type,
                    instrument_id=instrument_id,
                    initial_cash=account.cash,
                    initial_inventory=inventory,
                )
            )

        self._participant_ids = ids
        self._started = True
        self.record_balances(period=0, phase="initial", exchange=exchange)

    def record_decision(
        self,
        *,
        period: int,
        agent_id: str,
        decision: TradingDecision,
    ) -> None:
        """Record one policy output, preserving HOLD decisions."""

        self._require_started()
        if not self.config.record_decisions:
            return
        self._decisions.append(
            DecisionRecord(
                period=period,
                agent_id=agent_id,
                kind=decision.kind.value,
                side=None if decision.side is None else decision.side.value,
                order_type=None if decision.order_type is None else decision.order_type.value,
                quantity=decision.quantity,
                price=decision.price,
                time_in_force=None
                if decision.time_in_force is None
                else decision.time_in_force.value,
            )
        )

    def record_cancellation(
        self,
        *,
        period: int,
        sequence_number: int,
        order: Order,
    ) -> None:
        """Record one successfully executed cancellation."""
        self._require_started()
        if not self.config.record_cancellations:
            return
        if isinstance(sequence_number, bool) or not isinstance(sequence_number, int):
            raise RecordingStateError("cancellation sequence_number must be an integer")
        if sequence_number < 0:
            raise RecordingStateError("cancellation sequence_number must be non-negative")
        if not isinstance(order, Order):
            raise TypeError("order must be an Order")
        if order.price is None:
            raise RecordingStateError("cancelled resting order must have a limit price")
        self._cancellations.append(
            CancellationRecord(
                period=period,
                sequence_number=sequence_number,
                agent_id=order.agent_id,
                order_id=order.order_id,
                order_sequence_number=order.sequence_number,
                instrument_id=order.instrument_id,
                side=order.side.value,
                limit_price=order.price,
                cancelled_quantity=order.remaining_quantity,
            )
        )

    def record_order(
        self,
        *,
        period: int,
        order: Order,
        exchange_result: ExchangeResult | None,
        rejection_type: str | None = None,
        rejection_message: str | None = None,
    ) -> None:
        """Record one submitted order as either committed or economically rejected."""

        self._require_started()
        if not self.config.record_orders:
            return
        accepted = exchange_result is not None
        if accepted and rejection_type is not None:
            raise RecordingStateError("accepted orders cannot carry rejection metadata")
        if not accepted and rejection_type is None:
            raise RecordingStateError("rejected orders require rejection_type")

        if exchange_result is None:
            executed_quantity = _ZERO
            remaining_quantity = order.remaining_quantity
            cancelled_quantity = _ZERO
            rested = False
        else:
            executed_quantity = exchange_result.executed_quantity
            remaining_quantity = exchange_result.final_order.remaining_quantity
            cancelled_quantity = exchange_result.cancelled_quantity
            rested = exchange_result.rested

        self._orders.append(
            OrderRecord(
                period=period,
                order_id=order.order_id,
                sequence_number=order.sequence_number,
                agent_id=order.agent_id,
                instrument_id=order.instrument_id,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                limit_price=order.price,
                submitted_at=order.submitted_at,
                time_in_force=order.time_in_force.value,
                accepted=accepted,
                executed_quantity=executed_quantity,
                remaining_quantity=remaining_quantity,
                cancelled_quantity=cancelled_quantity,
                rested=rested,
                rejection_type=rejection_type,
                rejection_message=rejection_message,
            )
        )

    def record_trade(self, *, period: int, trade: Trade) -> None:
        """Record one committed trade exactly once."""

        self._require_started()
        if not self.config.record_trades:
            return
        self._trades.append(
            TradeRecord(
                period=period,
                trade_id=trade.trade_id,
                sequence_number=trade.sequence_number,
                instrument_id=trade.instrument_id,
                buy_order_id=trade.buy_order_id,
                sell_order_id=trade.sell_order_id,
                buyer_id=trade.buyer_id,
                seller_id=trade.seller_id,
                maker_order_id=trade.maker_order_id,
                taker_order_id=trade.taker_order_id,
                price=trade.price,
                quantity=trade.quantity,
                executed_at=trade.executed_at,
                buyer_fee=trade.buyer_fee,
                seller_fee=trade.seller_fee,
            )
        )

    def record_market_state(
        self,
        *,
        period: int,
        fundamental_value: Decimal,
        snapshot: OrderBookSnapshot,
        last_trade_price: Decimal | None,
        price_change: Decimal | None,
        fee_balance: Decimal,
    ) -> None:
        """Record one completed-period aggregate book and reference-value state."""

        self._require_started()
        if not self.config.record_market_states:
            return
        bid_depth = sum((level.total_quantity for level in snapshot.bids), start=_ZERO)
        ask_depth = sum((level.total_quantity for level in snapshot.asks), start=_ZERO)
        self._market_states.append(
            MarketStateRecord(
                period=period,
                instrument_id=snapshot.instrument_id,
                fundamental_value=fundamental_value,
                best_bid=snapshot.best_bid,
                best_ask=snapshot.best_ask,
                mid_price=snapshot.mid_price,
                spread=snapshot.spread,
                bid_depth=bid_depth,
                ask_depth=ask_depth,
                imbalance=snapshot.imbalance,
                order_count=snapshot.order_count,
                last_trade_price=last_trade_price,
                price_change=price_change,
                fee_balance=fee_balance,
            )
        )

    def record_balances(
        self,
        *,
        period: int,
        phase: RecordingPhase,
        exchange: Exchange,
    ) -> None:
        """Record exact cash and single-instrument inventory for known participants."""

        self._require_started()
        instrument_id = exchange.instrument.instrument_id
        for agent_id in self._participant_ids:
            if self.config.record_accounts:
                self._accounts.append(
                    AccountRecord(
                        period=period,
                        phase=phase,
                        agent_id=agent_id,
                        cash=exchange.account(agent_id).cash,
                    )
                )
            if self.config.record_positions:
                self._positions.append(
                    PositionRecord(
                        period=period,
                        phase=phase,
                        agent_id=agent_id,
                        instrument_id=instrument_id,
                        quantity=exchange.portfolio(agent_id).quantity(instrument_id),
                    )
                )

    def _require_started(self) -> None:
        if not self._started:
            raise RecordingStateError("finance research recorder has not been started")
