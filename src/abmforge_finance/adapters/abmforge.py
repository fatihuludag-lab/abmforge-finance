"""ABMForge lifecycle adapter for deterministic finance orchestration."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from abmforge.core.model import Model

from abmforge_finance.agents import Trader
from abmforge_finance.domain import (
    MarketObservation,
    Order,
    OrderType,
    Side,
    TimeInForce,
    Trade,
    TradingDecision,
    TradingPlan,
)
from abmforge_finance.exceptions import (
    FinanceAdapterNotInitializedError,
    FinanceClockDriftError,
    FinanceSeedUnavailableError,
    InsufficientAvailableInventoryError,
    InsufficientBuyingPowerError,
    InvalidFinanceComponentsError,
    InvalidPriceError,
    InvalidQuantityError,
    InvalidTradingPlanError,
    UnknownParticipantError,
)
from abmforge_finance.market import (
    Exchange,
    ExchangeResult,
    FundamentalValueProcess,
    MarketClock,
    OrderBookSnapshot,
)
from abmforge_finance.recording import FinanceResearchRecorder

_ZERO = Decimal("0")
_FINANCE_SEED_NAMESPACE = b"abmforge-finance.component-seed.v1"


@dataclass(frozen=True, slots=True)
class FinanceComponents:
    """Framework-independent components owned by one ABMForge finance model."""

    exchange: Exchange
    clock: MarketClock
    fundamental: FundamentalValueProcess
    traders: tuple[Trader, ...]
    research_recorder: FinanceResearchRecorder | None = None


@dataclass(frozen=True, slots=True)
class FinanceCancellationOutcome:
    """Audit record for one successfully executed cancellation."""

    sequence_number: int
    agent_id: str
    order: Order


@dataclass(frozen=True, slots=True)
class FinanceOrderOutcome:
    """Audit record for one trader decision within a completed finance period."""

    agent_id: str
    decision: TradingDecision
    order: Order | None = None
    exchange_result: ExchangeResult | None = None
    rejection_type: str | None = None
    rejection_message: str | None = None

    @property
    def rejected(self) -> bool:
        """Return whether an order was rejected as an expected economic outcome."""

        return self.rejection_type is not None

    @property
    def trades(self) -> tuple[Trade, ...]:
        """Return committed trades produced by this outcome."""

        if self.exchange_result is None:
            return ()
        return self.exchange_result.trades


@dataclass(frozen=True, slots=True)
class FinanceStepResult:
    """Immutable audit summary for one completed finance period."""

    period: int
    fundamental_value: Decimal
    pre_snapshot: OrderBookSnapshot
    post_snapshot: OrderBookSnapshot
    outcomes: tuple[FinanceOrderOutcome, ...]
    last_trade_price: Decimal | None
    price_change: Decimal | None
    fee_balance: Decimal
    cancellations: tuple[FinanceCancellationOutcome, ...] = ()

    @property
    def trades(self) -> tuple[Trade, ...]:
        """Return all committed trades in deterministic order."""

        return tuple(trade for outcome in self.outcomes for trade in outcome.trades)

    @property
    def trade_count(self) -> int:
        """Return the number of committed trades in this period."""

        return len(self.trades)

    @property
    def cancellation_count(self) -> int:
        """Return the number of successful resting-order cancellations."""

        return len(self.cancellations)

    @property
    def rejection_count(self) -> int:
        """Return the number of expected order rejections in this period."""

        return sum(outcome.rejected for outcome in self.outcomes)

    @property
    def hold_count(self) -> int:
        """Return the number of explicit HOLD decisions in this period."""

        return sum(outcome.decision.is_hold for outcome in self.outcomes)

    @property
    def executed_quantity(self) -> Decimal:
        """Return exact aggregate executed quantity for the period."""

        return sum((trade.quantity for trade in self.trades), start=_ZERO)


class FinanceABMModel(Model, ABC):
    """ABMForge ``Model`` subclass that orchestrates the finance research core.

    Subclasses implement :meth:`build_finance_components` using only explicit model
    parameters and seeds. ABMForge remains responsible for scenario construction,
    model lifecycle, model ``steps/time``, and recorder collection. This adapter owns
    the finance-specific per-period sequence: build a common pre-action information
    set, collect policy decisions, construct deterministic domain orders, submit them
    to :class:`Exchange`, and advance :class:`MarketClock` exactly once.

    Finance traders deliberately remain outside ``Model.agents``. Their authoritative
    cash and inventory live in ``Exchange`` and finance-specific agent tables are
    deferred to the dedicated recorder milestone.
    """

    def __init__(
        self,
        *,
        parameters: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__(parameters=parameters, seed=seed)
        self._finance_components: FinanceComponents | None = None
        self._finance_traders: tuple[Trader, ...] = ()
        self._next_order_sequence = 0
        self._last_step_result: FinanceStepResult | None = None
        self._last_trade_price: Decimal | None = None
        self._last_price_change: Decimal | None = None
        self._finance_component_seeds: dict[str, int] = {}

    @abstractmethod
    def build_finance_components(self) -> FinanceComponents:
        """Construct the framework-independent finance components for this run."""

    @property
    def finance(self) -> FinanceComponents:
        """Return validated finance components after :meth:`setup`."""

        if self._finance_components is None:
            raise FinanceAdapterNotInitializedError("finance components are not initialized")
        return self._finance_components

    @property
    def last_finance_step(self) -> FinanceStepResult | None:
        """Return the most recently completed finance period, if any."""

        return self._last_step_result

    @property
    def next_order_sequence(self) -> int:
        """Return the sequence that the adapter will assign to the next order decision."""

        return self._next_order_sequence

    def finance_seed(self, name: str) -> int:
        """Derive and cache one call-order-independent component seed.

        An explicit ABMForge model seed is required. Equal model seed and equal
        normalized component name produce the same unsigned 64-bit seed regardless of
        component construction order or unrelated random draws.
        """

        if self.seed is None:
            raise FinanceSeedUnavailableError(
                "finance_seed() requires an explicit ABMForge model seed"
            )
        if not isinstance(name, str) or not name.strip():
            raise ValueError("finance component seed name must be a non-empty string")
        normalized = name.strip()
        existing = self._finance_component_seeds.get(normalized)
        if existing is not None:
            return existing

        digest = hashlib.sha256()
        digest.update(_FINANCE_SEED_NAMESPACE)
        digest.update(b"\0")
        digest.update(str(int(self.seed)).encode("ascii"))
        digest.update(b"\0")
        digest.update(normalized.encode("utf-8"))
        derived = int.from_bytes(digest.digest()[:8], byteorder="big", signed=False)
        self._finance_component_seeds[normalized] = derived
        return derived

    def setup(self) -> None:
        """Build and validate finance components, then register model-level metrics."""

        if self._finance_components is not None:
            raise InvalidFinanceComponentsError("finance setup may only run once")
        components = self.build_finance_components()
        self._validate_components(components)
        sorted_traders = tuple(sorted(components.traders, key=lambda trader: trader.agent_id))
        self._finance_components = FinanceComponents(
            exchange=components.exchange,
            clock=components.clock,
            fundamental=components.fundamental,
            traders=sorted_traders,
            research_recorder=components.research_recorder,
        )
        self._finance_traders = sorted_traders
        self._next_order_sequence = components.exchange.next_submission_sequence
        if components.research_recorder is not None:
            components.research_recorder.start(components.exchange, sorted_traders)
        self._register_finance_metrics()

    def step(self) -> None:
        """Execute one deterministic finance period under the ABMForge lifecycle."""

        components = self.finance
        self._require_clock_alignment()
        period = components.clock.current_step
        fundamental_value = components.fundamental.value_at(period)
        pre_snapshot = components.exchange.snapshot()

        planned: list[tuple[Trader, TradingPlan]] = []
        for trader in self._finance_traders:
            observation = self._build_observation(
                trader=trader,
                period=period,
                fundamental_value=fundamental_value,
                snapshot=pre_snapshot,
            )
            planned.append(
                (
                    trader,
                    trader.plan(
                        observation,
                        active_order_ids=components.exchange.active_order_ids(trader.agent_id),
                    ),
                )
            )

        self._validate_cancellation_plans(planned)

        cancellations: list[FinanceCancellationOutcome] = []
        cancellation_sequence = 0
        for trader, plan in planned:
            for intent in plan.cancellations:
                cancelled_order = components.exchange.cancel(
                    intent.order_id,
                    participant_id=trader.agent_id,
                )
                cancellations.append(
                    FinanceCancellationOutcome(
                        sequence_number=cancellation_sequence,
                        agent_id=trader.agent_id,
                        order=cancelled_order,
                    )
                )
                cancellation_sequence += 1

        outcomes: list[FinanceOrderOutcome] = []
        for trader, plan in planned:
            decision = plan.decision
            if decision.is_hold:
                outcomes.append(
                    FinanceOrderOutcome(
                        agent_id=trader.agent_id,
                        decision=decision,
                    )
                )
                continue
            order = self._order_from_decision(
                agent_id=trader.agent_id,
                decision=decision,
                period=period,
            )
            try:
                exchange_result = components.exchange.submit(order)
            except (
                InsufficientAvailableInventoryError,
                InsufficientBuyingPowerError,
                InvalidPriceError,
                InvalidQuantityError,
            ) as exc:
                outcomes.append(
                    FinanceOrderOutcome(
                        agent_id=trader.agent_id,
                        decision=decision,
                        order=order,
                        rejection_type=type(exc).__name__,
                        rejection_message=str(exc),
                    )
                )
            else:
                outcomes.append(
                    FinanceOrderOutcome(
                        agent_id=trader.agent_id,
                        decision=decision,
                        order=order,
                        exchange_result=exchange_result,
                    )
                )
        trades = tuple(
            trade
            for outcome in outcomes
            if outcome.exchange_result is not None
            for trade in outcome.exchange_result.trades
        )
        previous_last_trade = self._last_trade_price
        if trades:
            self._last_trade_price = trades[-1].price
            self._last_price_change = (
                None
                if previous_last_trade is None
                else self._last_trade_price - previous_last_trade
            )
        elif previous_last_trade is not None:
            self._last_price_change = _ZERO

        post_snapshot = components.exchange.snapshot()
        self._last_step_result = FinanceStepResult(
            period=period,
            fundamental_value=fundamental_value,
            pre_snapshot=pre_snapshot,
            post_snapshot=post_snapshot,
            outcomes=tuple(outcomes),
            last_trade_price=self._last_trade_price,
            price_change=self._last_price_change,
            fee_balance=components.exchange.fee_balance,
            cancellations=tuple(cancellations),
        )
        self._record_research_step(self._last_step_result)
        components.clock.advance()

    def _validate_cancellation_plans(
        self,
        planned: list[tuple[Trader, TradingPlan]],
    ) -> None:
        """Validate all cancellation intents before mutating the Exchange."""
        seen: set[str] = set()
        exchange = self.finance.exchange
        for trader, plan in planned:
            for intent in plan.cancellations:
                if intent.order_id in seen:
                    raise InvalidTradingPlanError(
                        f"order_id {intent.order_id!r} is cancelled more than once "
                        "in the same finance period"
                    )
                seen.add(intent.order_id)
                order = exchange.order(intent.order_id)
                if order is None:
                    raise InvalidTradingPlanError(
                        f"cancellation order_id {intent.order_id!r} is not active"
                    )
                if order.agent_id != trader.agent_id:
                    raise InvalidTradingPlanError(
                        f"trader {trader.agent_id!r} cannot cancel order_id "
                        f"{intent.order_id!r} owned by {order.agent_id!r}"
                    )

    def _validate_components(self, components: object) -> None:
        if not isinstance(components, FinanceComponents):
            raise InvalidFinanceComponentsError(
                "build_finance_components() must return FinanceComponents"
            )
        if not isinstance(components.exchange, Exchange):
            raise InvalidFinanceComponentsError("exchange must be an Exchange")
        if not isinstance(components.clock, MarketClock):
            raise InvalidFinanceComponentsError("clock must be a MarketClock")
        if not callable(getattr(components.fundamental, "value_at", None)):
            raise InvalidFinanceComponentsError(
                "fundamental must implement FundamentalValueProcess.value_at()"
            )
        if not isinstance(components.traders, tuple) or not all(
            isinstance(trader, Trader) for trader in components.traders
        ):
            raise InvalidFinanceComponentsError("traders must be a tuple of Trader values")
        if components.research_recorder is not None and not isinstance(
            components.research_recorder, FinanceResearchRecorder
        ):
            raise InvalidFinanceComponentsError(
                "research_recorder must be a FinanceResearchRecorder or None"
            )
        trader_ids = tuple(trader.agent_id for trader in components.traders)
        if len(set(trader_ids)) != len(trader_ids):
            raise InvalidFinanceComponentsError("trader agent_id values must be unique")
        if components.clock.current_step != self.steps:
            raise FinanceClockDriftError(
                "finance clock must equal ABMForge model.steps during setup"
            )
        last_submitted_at = components.exchange.last_submitted_at
        if last_submitted_at is not None and last_submitted_at > components.clock.current_step:
            raise FinanceClockDriftError(
                "exchange submission time cannot be ahead of the finance clock"
            )
        for trader in components.traders:
            try:
                components.exchange.account(trader.agent_id)
                components.exchange.portfolio(trader.agent_id)
            except UnknownParticipantError as exc:
                raise InvalidFinanceComponentsError(
                    f"trader {trader.agent_id!r} must be registered with Exchange"
                ) from exc

    def _require_clock_alignment(self) -> None:
        finance_step = self.finance.clock.current_step
        if finance_step != self.steps:
            raise FinanceClockDriftError(
                f"finance clock {finance_step} does not match ABMForge model.steps {self.steps}"
            )

    def _build_observation(
        self,
        *,
        trader: Trader,
        period: int,
        fundamental_value: Decimal,
        snapshot: OrderBookSnapshot,
    ) -> MarketObservation:
        exchange = self.finance.exchange
        bid_depth = sum((level.total_quantity for level in snapshot.bids), start=_ZERO)
        ask_depth = sum((level.total_quantity for level in snapshot.asks), start=_ZERO)
        return MarketObservation(
            step=period,
            instrument_id=exchange.instrument.instrument_id,
            fundamental_value=fundamental_value,
            best_bid=snapshot.best_bid,
            best_ask=snapshot.best_ask,
            mid_price=snapshot.mid_price,
            spread=snapshot.spread,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            imbalance=snapshot.imbalance,
            last_trade_price=self._last_trade_price,
            price_change=self._last_price_change,
            cash=exchange.account(trader.agent_id).cash,
            inventory=exchange.portfolio(trader.agent_id).quantity(
                exchange.instrument.instrument_id
            ),
        )

    def _order_from_decision(
        self,
        *,
        agent_id: str,
        decision: TradingDecision,
        period: int,
    ) -> Order:
        if decision.is_hold:
            raise ValueError("HOLD decisions cannot be converted to Order")
        sequence = self._next_order_sequence
        self._next_order_sequence += 1
        return Order(
            order_id=f"finance-order-{sequence:012d}",
            agent_id=agent_id,
            instrument_id=self.finance.exchange.instrument.instrument_id,
            side=cast(Side, decision.side),
            order_type=cast(OrderType, decision.order_type),
            quantity=cast(Decimal, decision.quantity),
            remaining_quantity=cast(Decimal, decision.quantity),
            price=decision.price,
            submitted_at=period,
            sequence_number=sequence,
            time_in_force=cast(TimeInForce, decision.time_in_force),
        )

    def _record_research_step(self, result: FinanceStepResult) -> None:
        recorder = self.finance.research_recorder
        if recorder is None:
            return
        for cancellation in result.cancellations:
            recorder.record_cancellation(
                period=result.period,
                sequence_number=cancellation.sequence_number,
                order=cancellation.order,
            )
        for outcome in result.outcomes:
            recorder.record_decision(
                period=result.period,
                agent_id=outcome.agent_id,
                decision=outcome.decision,
            )
            if outcome.order is not None:
                recorder.record_order(
                    period=result.period,
                    order=outcome.order,
                    exchange_result=outcome.exchange_result,
                    rejection_type=outcome.rejection_type,
                    rejection_message=outcome.rejection_message,
                )
            for trade in outcome.trades:
                recorder.record_trade(period=result.period, trade=trade)
        recorder.record_market_state(
            period=result.period,
            fundamental_value=result.fundamental_value,
            snapshot=result.post_snapshot,
            last_trade_price=result.last_trade_price,
            price_change=result.price_change,
            fee_balance=result.fee_balance,
        )
        recorder.record_balances(
            period=result.period,
            phase="post",
            exchange=self.finance.exchange,
        )

    def _register_finance_metrics(self) -> None:
        self.record.metric("finance_period_completed", lambda _model: self._metric_period())
        self.record.metric(
            "finance_fundamental_value",
            lambda _model: self._metric_decimal("fundamental_value"),
        )
        self.record.metric("finance_trade_count", lambda _model: self._metric_int("trade_count"))
        self.record.metric(
            "finance_executed_quantity",
            lambda _model: self._metric_decimal("executed_quantity"),
        )
        self.record.metric(
            "finance_cancellation_count",
            lambda _model: self._metric_int("cancellation_count"),
        )
        self.record.metric(
            "finance_rejection_count",
            lambda _model: self._metric_int("rejection_count"),
        )
        self.record.metric("finance_hold_count", lambda _model: self._metric_int("hold_count"))
        for metric_name, attribute in (
            ("finance_best_bid", "best_bid"),
            ("finance_best_ask", "best_ask"),
            ("finance_mid_price", "mid_price"),
            ("finance_spread", "spread"),
            ("finance_imbalance", "imbalance"),
        ):
            self._register_snapshot_metric(metric_name, attribute)
        self.record.metric(
            "finance_last_trade_price",
            lambda _model: self._metric_decimal("last_trade_price"),
            when=lambda _model: self._has_result_value("last_trade_price"),
        )
        self.record.metric(
            "finance_price_change",
            lambda _model: self._metric_decimal("price_change"),
            when=lambda _model: self._has_result_value("price_change"),
        )
        self.record.metric(
            "finance_fee_balance",
            lambda _model: self._metric_decimal("fee_balance"),
        )

    def _register_snapshot_metric(self, metric_name: str, attribute: str) -> None:
        def model_metric(_model: Model) -> float | None:
            return self._metric_snapshot(attribute)

        def predicate(_model: Model) -> bool:
            return self._has_snapshot_metric(attribute)

        self.record.metric(metric_name, model_metric, when=predicate)

    def _metric_period(self) -> int | None:
        return None if self._last_step_result is None else self._last_step_result.period

    def _metric_int(self, attribute: str) -> int | None:
        result = self._last_step_result
        if result is None:
            return None
        return int(getattr(result, attribute))

    def _metric_decimal(self, attribute: str) -> float | None:
        result = self._last_step_result
        if result is None:
            return None
        return float(getattr(result, attribute))

    def _metric_snapshot(self, attribute: str) -> float | None:
        result = self._last_step_result
        if result is None:
            return None
        value = getattr(result.post_snapshot, attribute)
        return None if value is None else float(value)

    def _has_snapshot_metric(self, attribute: str) -> bool:
        result = self._last_step_result
        return result is not None and getattr(result.post_snapshot, attribute) is not None

    def _has_result_value(self, attribute: str) -> bool:
        result = self._last_step_result
        return result is not None and getattr(result, attribute) is not None
