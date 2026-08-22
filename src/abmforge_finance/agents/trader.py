"""Framework-independent trader identity and policy composition."""

from __future__ import annotations

from dataclasses import dataclass

from abmforge_finance.domain import MarketObservation, TradingDecision, TradingPlan
from abmforge_finance.exceptions import InvalidPolicyError, InvalidTraderError
from abmforge_finance.policies import TradingPlanPolicy, TradingPolicy


@dataclass(frozen=True, slots=True)
class Trader:
    """Bind stable trader identity to policy logic without duplicating market state.

    Cash and inventory remain authoritative in :class:`Exchange`; observations carry
    immutable snapshots of those values. Existing one-decision policies and new
    cancel/replace-aware planning policies share the same stable trader identity.
    """

    agent_id: str
    policy: TradingPolicy | TradingPlanPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise InvalidTraderError("agent_id must be a non-empty string")
        if not isinstance(self.policy, (TradingPolicy, TradingPlanPolicy)):
            raise InvalidTraderError("policy must implement TradingPolicy or TradingPlanPolicy")

    def decide(self, observation: MarketObservation) -> TradingDecision:
        """Delegate to a legacy one-decision policy with the original validation."""

        if not isinstance(observation, MarketObservation):
            raise InvalidTraderError("observation must be a MarketObservation")
        if not isinstance(self.policy, TradingPolicy):
            raise InvalidTraderError("plan-only policy does not implement decide()")

        decision = self.policy.decide(observation, agent_id=self.agent_id)
        if not isinstance(decision, TradingDecision):
            raise InvalidPolicyError("policy must return a TradingDecision")
        return decision

    def plan(
        self,
        observation: MarketObservation,
        *,
        active_order_ids: tuple[str, ...] = (),
    ) -> TradingPlan:
        """Normalize legacy and cancel/replace-aware policies to one plan contract."""

        if not isinstance(observation, MarketObservation):
            raise InvalidTraderError("observation must be a MarketObservation")
        if not isinstance(active_order_ids, tuple) or not all(
            isinstance(order_id, str) and order_id.strip() for order_id in active_order_ids
        ):
            raise InvalidTraderError("active_order_ids must be a tuple of non-empty strings")

        if isinstance(self.policy, TradingPlanPolicy):
            plan = self.policy.plan(
                observation,
                agent_id=self.agent_id,
                active_order_ids=active_order_ids,
            )
            if not isinstance(plan, TradingPlan):
                raise InvalidPolicyError("planning policy must return a TradingPlan")
            return plan

        if isinstance(self.policy, TradingPolicy):
            decision = self.policy.decide(observation, agent_id=self.agent_id)
            if not isinstance(decision, TradingDecision):
                raise InvalidPolicyError("policy must return a TradingDecision")
            return TradingPlan.from_decision(decision)

        raise InvalidTraderError("trader policy no longer satisfies a supported protocol")

    def with_policy(self, policy: TradingPolicy | TradingPlanPolicy) -> Trader:
        """Return the same trader identity composed with a replacement policy."""

        return Trader(agent_id=self.agent_id, policy=policy)
