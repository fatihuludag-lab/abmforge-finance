"""Immutable in-memory finance research dataset."""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from dataclasses import dataclass

from abmforge_finance.exceptions import InvalidFinanceDatasetError
from abmforge_finance.recording.schema import (
    FINANCE_DATASET_SCHEMA_VERSION,
    AccountRecord,
    DecisionRecord,
    MarketStateRecord,
    OrderRecord,
    ParticipantRecord,
    PositionRecord,
    TradeRecord,
)


def _require_unique(values: Iterable[Hashable], *, label: str) -> None:
    seen: set[Hashable] = set()
    for value in values:
        if value in seen:
            raise InvalidFinanceDatasetError(f"duplicate {label}: {value!r}")
        seen.add(value)


@dataclass(frozen=True, slots=True)
class FinanceResearchDataset:
    """Validated immutable snapshot of finance-specific research tables."""

    schema_version: str = FINANCE_DATASET_SCHEMA_VERSION
    participants: tuple[ParticipantRecord, ...] = ()
    decisions: tuple[DecisionRecord, ...] = ()
    orders: tuple[OrderRecord, ...] = ()
    trades: tuple[TradeRecord, ...] = ()
    market_states: tuple[MarketStateRecord, ...] = ()
    accounts: tuple[AccountRecord, ...] = ()
    positions: tuple[PositionRecord, ...] = ()

    @property
    def row_counts(self) -> dict[str, int]:
        """Return deterministic table row counts."""

        return {
            "participants": len(self.participants),
            "decisions": len(self.decisions),
            "orders": len(self.orders),
            "trades": len(self.trades),
            "market_states": len(self.market_states),
            "accounts": len(self.accounts),
            "positions": len(self.positions),
        }

    def validate(self) -> None:
        """Validate schema identity, event keys, phases, and non-negative periods."""

        if self.schema_version != FINANCE_DATASET_SCHEMA_VERSION:
            raise InvalidFinanceDatasetError(
                f"unsupported finance dataset schema_version {self.schema_version!r}"
            )

        _require_unique((row.agent_id for row in self.participants), label="participant agent_id")
        _require_unique(
            ((row.period, row.agent_id) for row in self.decisions),
            label="decision (period, agent_id)",
        )
        _require_unique((row.order_id for row in self.orders), label="order_id")
        _require_unique((row.trade_id for row in self.trades), label="trade_id")
        _require_unique((row.period for row in self.market_states), label="market-state period")
        _require_unique(
            ((row.period, row.phase, row.agent_id) for row in self.accounts),
            label="account (period, phase, agent_id)",
        )
        _require_unique(
            ((row.period, row.phase, row.agent_id, row.instrument_id) for row in self.positions),
            label="position (period, phase, agent_id, instrument_id)",
        )

        if (
            any(row.period < 0 for row in self.decisions)
            or any(row.period < 0 for row in self.orders)
            or any(row.period < 0 for row in self.trades)
            or any(row.period < 0 for row in self.market_states)
            or any(row.period < 0 for row in self.accounts)
            or any(row.period < 0 for row in self.positions)
        ):
            raise InvalidFinanceDatasetError("recorded periods must be non-negative")
        if any(row.phase not in ("initial", "post") for row in self.accounts) or any(
            row.phase not in ("initial", "post") for row in self.positions
        ):
            raise InvalidFinanceDatasetError("recording phase must be 'initial' or 'post'")
