"""Framework-independent trader identity composed with a swappable policy."""

from __future__ import annotations

from dataclasses import dataclass

from abmforge_finance.domain import MarketObservation, TradingDecision
from abmforge_finance.exceptions import InvalidPolicyError, InvalidTraderError
from abmforge_finance.policies import TradingPolicy


@dataclass(frozen=True, slots=True)
class Trader:
    """Bind stable trader identity to policy logic without duplicating market state.

    Cash and inventory remain authoritative in :class:`Exchange`; observations carry
    immutable snapshots of those values. This avoids a second mutable accounting source
    of truth inside the trader object.
    """

    agent_id: str
    policy: TradingPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise InvalidTraderError("agent_id must be a non-empty string")
        if not isinstance(self.policy, TradingPolicy):
            raise InvalidTraderError("policy must implement TradingPolicy")

    def decide(self, observation: MarketObservation) -> TradingDecision:
        """Delegate one immutable observation to the configured trading policy."""

        if not isinstance(observation, MarketObservation):
            raise InvalidTraderError("observation must be a MarketObservation")
        decision = self.policy.decide(observation, agent_id=self.agent_id)
        if not isinstance(decision, TradingDecision):
            raise InvalidPolicyError("policy must return a TradingDecision")
        return decision

    def with_policy(self, policy: TradingPolicy) -> Trader:
        """Return the same trader identity composed with a replacement policy."""

        return Trader(agent_id=self.agent_id, policy=policy)
