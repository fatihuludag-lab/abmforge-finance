"""Stateless explicitly seeded noise-trading baseline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain import MarketObservation, Side, TradingDecision
from abmforge_finance.exceptions import InvalidPolicyError
from abmforge_finance.policies.base import validate_positive_quantity

_MAX_SEED = (1 << 64) - 1
_BASIS_POINTS = 10_000


def _validate_seed(seed: object) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise InvalidPolicyError("seed must be an integer")
    if seed < 0 or seed > _MAX_SEED:
        raise InvalidPolicyError(f"seed must be in [0, {_MAX_SEED}]")
    return seed


def _validate_activity_bps(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidPolicyError("activity_bps must be an integer")
    if value < 0 or value > _BASIS_POINTS:
        raise InvalidPolicyError("activity_bps must be in [0, 10000]")
    return value


@dataclass(frozen=True, slots=True)
class NoisePolicy:
    """Emit deterministic pseudo-random buy/sell/hold decisions from explicit inputs.

    The policy is stateless. A SHA-256 digest of ``seed``, agent identity, instrument,
    and market step determines activity and side. Query order and agent activation order
    therefore cannot change an individual decision under identical inputs.
    """

    quantity: Decimal
    seed: int
    activity_bps: int = 5_000

    def __post_init__(self) -> None:
        validate_positive_quantity(self.quantity)
        _validate_seed(self.seed)
        _validate_activity_bps(self.activity_bps)

    def decide(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
    ) -> TradingDecision:
        """Return a reproducible market buy, market sell, or hold decision."""

        if not isinstance(observation, MarketObservation):
            raise InvalidPolicyError("observation must be a MarketObservation")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise InvalidPolicyError("agent_id must be a non-empty string")
        payload = (
            f"{self.seed}|{agent_id}|{observation.instrument_id}|{observation.step}"
        ).encode()
        digest = hashlib.sha256(payload).digest()
        activity_draw = int.from_bytes(digest[:8], "big") % _BASIS_POINTS
        if activity_draw >= self.activity_bps:
            return TradingDecision.hold()
        side = Side.BUY if digest[8] % 2 == 0 else Side.SELL
        return TradingDecision.market(side, self.quantity)
