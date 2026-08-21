"""Immutable schema-v1 rows for finance research recording."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

FINANCE_DATASET_SCHEMA_VERSION = "1.0"
RecordingPhase = Literal["initial", "post"]


@dataclass(frozen=True, slots=True)
class ParticipantRecord:
    """One finance participant at recorder start."""

    agent_id: str
    policy_type: str
    instrument_id: str
    initial_cash: Decimal
    initial_inventory: Decimal


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """One policy decision, including explicit HOLD decisions."""

    period: int
    agent_id: str
    kind: str
    side: str | None
    order_type: str | None
    quantity: Decimal | None
    price: Decimal | None
    time_in_force: str | None


@dataclass(frozen=True, slots=True)
class OrderRecord:
    """One submitted order and its committed or rejected outcome."""

    period: int
    order_id: str
    sequence_number: int
    agent_id: str
    instrument_id: str
    side: str
    order_type: str
    quantity: Decimal
    limit_price: Decimal | None
    submitted_at: int | float
    time_in_force: str
    accepted: bool
    executed_quantity: Decimal
    remaining_quantity: Decimal
    cancelled_quantity: Decimal
    rested: bool
    rejection_type: str | None
    rejection_message: str | None


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """One committed execution with maker/taker and fee provenance."""

    period: int
    trade_id: str
    sequence_number: int
    instrument_id: str
    buy_order_id: str
    sell_order_id: str
    buyer_id: str
    seller_id: str
    maker_order_id: str
    taker_order_id: str
    price: Decimal
    quantity: Decimal
    executed_at: int | float
    buyer_fee: Decimal
    seller_fee: Decimal


@dataclass(frozen=True, slots=True)
class MarketStateRecord:
    """One completed-period market state."""

    period: int
    instrument_id: str
    fundamental_value: Decimal
    best_bid: Decimal | None
    best_ask: Decimal | None
    mid_price: Decimal | None
    spread: Decimal | None
    bid_depth: Decimal
    ask_depth: Decimal
    imbalance: Decimal | None
    order_count: int
    last_trade_price: Decimal | None
    price_change: Decimal | None
    fee_balance: Decimal


@dataclass(frozen=True, slots=True)
class AccountRecord:
    """Exact participant cash at one recording phase."""

    period: int
    phase: RecordingPhase
    agent_id: str
    cash: Decimal


@dataclass(frozen=True, slots=True)
class PositionRecord:
    """Exact participant inventory at one recording phase."""

    period: int
    phase: RecordingPhase
    agent_id: str
    instrument_id: str
    quantity: Decimal
