"""Deterministic population narrative-homogeneity treatments and measurements."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain import NarrativeDirection, NarrativeExposure, NarrativeState
from abmforge_finance.exceptions import InvalidNarrativeTreatmentError
from abmforge_finance.policies import NarrativePolicy
from abmforge_finance.recording import FinanceResearchDataset

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")


def _non_empty_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidNarrativeTreatmentError(f"{field_name} must be a non-empty string")
    return value.strip()


def _unit_interval(value: object, *, field_name: str, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise InvalidNarrativeTreatmentError(f"{field_name} must be a finite Decimal")
    if value < _ZERO or value > _ONE or (positive and value == _ZERO):
        bound = "(0, 1]" if positive else "[0, 1]"
        raise InvalidNarrativeTreatmentError(f"{field_name} must be in {bound}")
    return value


def _non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidNarrativeTreatmentError(f"{field_name} must be a non-negative integer")
    return value


def _concentration(buys: int, sells: int) -> Decimal | None:
    total = buys + sells
    if total == 0:
        return None
    return Decimal(abs(buys - sells)) / Decimal(total)


def _decimal_label(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


@dataclass(frozen=True, slots=True)
class NarrativeAgentAssignment:
    """One deterministic agent-to-direction assignment within a treatment."""

    agent_id: str
    direction: NarrativeDirection
    narrative_id: str
    is_focal: bool

    def __post_init__(self) -> None:
        _non_empty_text(self.agent_id, field_name="agent_id")
        _non_empty_text(self.narrative_id, field_name="narrative_id")
        if not isinstance(self.direction, NarrativeDirection):
            raise InvalidNarrativeTreatmentError("direction must be a NarrativeDirection")
        if self.direction is NarrativeDirection.NEUTRAL:
            raise InvalidNarrativeTreatmentError(
                "population assignments must be directionally active"
            )
        if not isinstance(self.is_focal, bool):
            raise InvalidNarrativeTreatmentError("is_focal must be a bool")


@dataclass(frozen=True, slots=True)
class NarrativeHomogeneityTreatment:
    """Exact binary-direction population treatment.

    ``homogeneity`` is assigned directional concentration

    ``abs(N_focal - N_opposing) / N``

    with ``N_focal >= N_opposing``. This makes zero a balanced population and one a
    fully focal-direction population.
    """

    treatment_id: str
    agent_ids: tuple[str, ...]
    homogeneity: Decimal
    focal_direction: NarrativeDirection
    strength: Decimal = Decimal("1")
    confidence: Decimal = Decimal("1")
    exposure_weight: Decimal = Decimal("1")
    active_from: int = 0
    active_until: int = 1

    def __post_init__(self) -> None:
        treatment_id = _non_empty_text(self.treatment_id, field_name="treatment_id")
        if not isinstance(self.agent_ids, tuple) or len(self.agent_ids) < 2:
            raise InvalidNarrativeTreatmentError(
                "agent_ids must be a tuple containing at least two agents"
            )

        normalized_ids = tuple(
            sorted(_non_empty_text(agent_id, field_name="agent_id") for agent_id in self.agent_ids)
        )
        if len(set(normalized_ids)) != len(normalized_ids):
            raise InvalidNarrativeTreatmentError("agent_ids must be unique")

        homogeneity = _unit_interval(self.homogeneity, field_name="homogeneity")
        if not isinstance(self.focal_direction, NarrativeDirection):
            raise InvalidNarrativeTreatmentError("focal_direction must be a NarrativeDirection")
        if self.focal_direction is NarrativeDirection.NEUTRAL:
            raise InvalidNarrativeTreatmentError("focal_direction must be BULLISH or BEARISH")

        _unit_interval(self.strength, field_name="strength", positive=True)
        _unit_interval(self.confidence, field_name="confidence", positive=True)
        _unit_interval(
            self.exposure_weight,
            field_name="exposure_weight",
            positive=True,
        )
        start = _non_negative_int(self.active_from, field_name="active_from")
        end = _non_negative_int(self.active_until, field_name="active_until")
        if end <= start:
            raise InvalidNarrativeTreatmentError("active_until must be greater than active_from")

        focal_exact = Decimal(len(normalized_ids)) * (_ONE + homogeneity) / _TWO
        if focal_exact != focal_exact.to_integral_value():
            raise InvalidNarrativeTreatmentError(
                "homogeneity is not exactly representable for the supplied population size"
            )

        object.__setattr__(self, "treatment_id", treatment_id)
        object.__setattr__(self, "agent_ids", normalized_ids)

    @property
    def population_size(self) -> int:
        return len(self.agent_ids)

    @property
    def focal_count(self) -> int:
        value = Decimal(self.population_size) * (_ONE + self.homogeneity) / _TWO
        return int(value)

    @property
    def opposing_count(self) -> int:
        return self.population_size - self.focal_count

    @property
    def opposing_direction(self) -> NarrativeDirection:
        if self.focal_direction is NarrativeDirection.BULLISH:
            return NarrativeDirection.BEARISH
        return NarrativeDirection.BULLISH

    @property
    def assigned_directional_concentration(self) -> Decimal:
        return Decimal(abs(self.focal_count - self.opposing_count)) / Decimal(self.population_size)

    @property
    def focal_narrative_id(self) -> str:
        return f"{self.treatment_id}:focal"

    @property
    def opposing_narrative_id(self) -> str:
        return f"{self.treatment_id}:opposing"

    @property
    def assignments(self) -> tuple[NarrativeAgentAssignment, ...]:
        output: list[NarrativeAgentAssignment] = []
        for index, agent_id in enumerate(self.agent_ids):
            is_focal = index < self.focal_count
            output.append(
                NarrativeAgentAssignment(
                    agent_id=agent_id,
                    direction=(self.focal_direction if is_focal else self.opposing_direction),
                    narrative_id=(
                        self.focal_narrative_id if is_focal else self.opposing_narrative_id
                    ),
                    is_focal=is_focal,
                )
            )
        return tuple(output)

    @property
    def focal_agent_ids(self) -> tuple[str, ...]:
        return tuple(item.agent_id for item in self.assignments if item.is_focal)

    @property
    def opposing_agent_ids(self) -> tuple[str, ...]:
        return tuple(item.agent_id for item in self.assignments if not item.is_focal)

    @property
    def narratives(self) -> tuple[NarrativeState, NarrativeState]:
        return (
            NarrativeState(
                self.focal_narrative_id,
                self.focal_direction,
                self.strength,
                self.confidence,
                self.active_from,
                self.active_until,
            ),
            NarrativeState(
                self.opposing_narrative_id,
                self.opposing_direction,
                self.strength,
                self.confidence,
                self.active_from,
                self.active_until,
            ),
        )

    @property
    def exposures(self) -> tuple[NarrativeExposure, ...]:
        return tuple(
            NarrativeExposure(
                item.agent_id,
                item.narrative_id,
                self.exposure_weight,
            )
            for item in self.assignments
        )

    def policy(
        self,
        *,
        quantity: Decimal,
        decision_threshold: Decimal = Decimal("0"),
    ) -> NarrativePolicy:
        """Return one shared policy implementing this fixed population assignment."""

        return NarrativePolicy(
            quantity=quantity,
            narratives=self.narratives,
            exposures=self.exposures,
            decision_threshold=decision_threshold,
        )


@dataclass(frozen=True, slots=True)
class NarrativeHomogeneityMeasurement:
    """Observed narrative-population synchronization for one dataset period."""

    period: int
    treatment_active: bool
    assigned_homogeneity: Decimal
    buy_decisions: int
    sell_decisions: int
    hold_decisions: int
    decision_concentration: Decimal | None
    accepted_buy_orders: int
    accepted_sell_orders: int
    rejected_orders: int
    accepted_order_concentration: Decimal | None

    @property
    def directional_decision_count(self) -> int:
        return self.buy_decisions + self.sell_decisions

    @property
    def accepted_directional_order_count(self) -> int:
        return self.accepted_buy_orders + self.accepted_sell_orders


def build_narrative_homogeneity_sweep(
    agent_ids: tuple[str, ...],
    *,
    homogeneities: tuple[Decimal, ...],
    focal_direction: NarrativeDirection,
    treatment_prefix: str = "narrative-homogeneity",
    strength: Decimal = Decimal("1"),
    confidence: Decimal = Decimal("1"),
    exposure_weight: Decimal = Decimal("1"),
    active_from: int = 0,
    active_until: int = 1,
) -> tuple[NarrativeHomogeneityTreatment, ...]:
    """Build an exact deterministic homogeneity treatment family.

    Agent IDs are canonicalized lexicographically inside every treatment. As
    homogeneity rises with all other inputs fixed, the focal-agent set is therefore
    nested rather than randomly reassigned.
    """

    prefix = _non_empty_text(treatment_prefix, field_name="treatment_prefix")
    if not isinstance(homogeneities, tuple) or not homogeneities:
        raise InvalidNarrativeTreatmentError("homogeneities must be a non-empty tuple")
    if len(set(homogeneities)) != len(homogeneities):
        raise InvalidNarrativeTreatmentError("homogeneities must be unique")

    return tuple(
        NarrativeHomogeneityTreatment(
            treatment_id=f"{prefix}={_decimal_label(homogeneity)}",
            agent_ids=agent_ids,
            homogeneity=homogeneity,
            focal_direction=focal_direction,
            strength=strength,
            confidence=confidence,
            exposure_weight=exposure_weight,
            active_from=active_from,
            active_until=active_until,
        )
        for homogeneity in homogeneities
    )


def measure_narrative_homogeneity(
    dataset: FinanceResearchDataset,
    treatment: NarrativeHomogeneityTreatment,
) -> tuple[NarrativeHomogeneityMeasurement, ...]:
    """Measure realized synchronization only within the assigned narrative population."""

    if not isinstance(dataset, FinanceResearchDataset):
        raise TypeError("dataset must be a FinanceResearchDataset")
    if not isinstance(treatment, NarrativeHomogeneityTreatment):
        raise TypeError("treatment must be a NarrativeHomogeneityTreatment")
    dataset.validate()

    agent_ids = set(treatment.agent_ids)
    periods = {row.period for row in dataset.market_states}
    periods.update(row.period for row in dataset.decisions if row.agent_id in agent_ids)
    periods.update(row.period for row in dataset.orders if row.agent_id in agent_ids)

    output: list[NarrativeHomogeneityMeasurement] = []
    for period in sorted(periods):
        decisions = tuple(
            row for row in dataset.decisions if row.period == period and row.agent_id in agent_ids
        )
        buy_decisions = sum(row.kind == "order" and row.side == "buy" for row in decisions)
        sell_decisions = sum(row.kind == "order" and row.side == "sell" for row in decisions)
        hold_decisions = sum(row.kind == "hold" for row in decisions)

        orders = tuple(
            row for row in dataset.orders if row.period == period and row.agent_id in agent_ids
        )
        accepted_buy = sum(row.accepted and row.side == "buy" for row in orders)
        accepted_sell = sum(row.accepted and row.side == "sell" for row in orders)
        rejected = sum(not row.accepted for row in orders)

        output.append(
            NarrativeHomogeneityMeasurement(
                period=period,
                treatment_active=(treatment.active_from <= period < treatment.active_until),
                assigned_homogeneity=treatment.assigned_directional_concentration,
                buy_decisions=buy_decisions,
                sell_decisions=sell_decisions,
                hold_decisions=hold_decisions,
                decision_concentration=_concentration(
                    buy_decisions,
                    sell_decisions,
                ),
                accepted_buy_orders=accepted_buy,
                accepted_sell_orders=accepted_sell,
                rejected_orders=rejected,
                accepted_order_concentration=_concentration(
                    accepted_buy,
                    accepted_sell,
                ),
            )
        )
    return tuple(output)
