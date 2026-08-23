"""Narrative synchronization and downstream market-stability evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain import NarrativeDirection, NarrativeState
from abmforge_finance.exceptions import InvalidNarrativeStabilityError
from abmforge_finance.experiments.narrative_homogeneity import (
    NarrativeHomogeneityTreatment,
    measure_narrative_homogeneity,
)
from abmforge_finance.metrics import (
    MarketPriceBasis,
    depth_asymmetry,
    depth_depletion,
    maximum_drawdown,
    realized_volatility,
    relative_absolute_fundamental_deviation,
    relative_spreads,
    spread_amplification,
    thin_side_depletion,
    thin_side_depth,
    total_depth,
)
from abmforge_finance.policies import NarrativePolicy
from abmforge_finance.recording import FinanceResearchDataset

_ZERO = Decimal("0")


def _positive_decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= _ZERO:
        raise InvalidNarrativeStabilityError(f"{field_name} must be a positive finite Decimal")
    return value


def _non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidNarrativeStabilityError(f"{field_name} must be a non-negative integer")
    return value


def _mean_decimal(values: tuple[Decimal | None, ...]) -> Decimal | None:
    defined = tuple(value for value in values if value is not None)
    if not defined:
        return None
    return sum(defined, start=_ZERO) / Decimal(len(defined))


def _quantity_concentration(
    buy_quantity: Decimal,
    sell_quantity: Decimal,
) -> Decimal | None:
    denominator = buy_quantity + sell_quantity
    if denominator == _ZERO:
        return None
    return abs(buy_quantity - sell_quantity) / denominator


def _opposite(direction: NarrativeDirection) -> NarrativeDirection:
    if direction is NarrativeDirection.BULLISH:
        return NarrativeDirection.BEARISH
    if direction is NarrativeDirection.BEARISH:
        return NarrativeDirection.BULLISH
    raise InvalidNarrativeStabilityError(
        "direction schedule must contain only BULLISH or BEARISH values"
    )


@dataclass(frozen=True, slots=True)
class NarrativeDirectionSchedule:
    """Exogenous focal-direction path held fixed across homogeneity treatments."""

    directions: tuple[NarrativeDirection, ...]
    start_step: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.directions, tuple) or not self.directions:
            raise InvalidNarrativeStabilityError("directions must be a non-empty tuple")
        if not all(
            isinstance(direction, NarrativeDirection)
            and direction is not NarrativeDirection.NEUTRAL
            for direction in self.directions
        ):
            raise InvalidNarrativeStabilityError(
                "directions must contain only BULLISH or BEARISH values"
            )
        _non_negative_int(self.start_step, field_name="start_step")

    @property
    def end_step(self) -> int:
        return self.start_step + len(self.directions)

    def narratives_for(
        self,
        treatment: NarrativeHomogeneityTreatment,
    ) -> tuple[NarrativeState, ...]:
        """Build focal and opposing narrative states for every scheduled step."""

        if not isinstance(treatment, NarrativeHomogeneityTreatment):
            raise TypeError("treatment must be a NarrativeHomogeneityTreatment")
        if treatment.active_from != self.start_step or treatment.active_until != self.end_step:
            raise InvalidNarrativeStabilityError(
                "direction schedule must exactly match the treatment active window"
            )
        if self.directions[0] is not treatment.focal_direction:
            raise InvalidNarrativeStabilityError(
                "the first scheduled direction must equal treatment.focal_direction"
            )

        states: list[NarrativeState] = []
        for offset, focal_direction in enumerate(self.directions):
            step = self.start_step + offset
            states.extend(
                (
                    NarrativeState(
                        treatment.focal_narrative_id,
                        focal_direction,
                        treatment.strength,
                        treatment.confidence,
                        step,
                        step + 1,
                    ),
                    NarrativeState(
                        treatment.opposing_narrative_id,
                        _opposite(focal_direction),
                        treatment.strength,
                        treatment.confidence,
                        step,
                        step + 1,
                    ),
                )
            )
        return tuple(states)

    def policy_for(
        self,
        treatment: NarrativeHomogeneityTreatment,
        *,
        quantity: Decimal,
        decision_threshold: Decimal = Decimal("0"),
    ) -> NarrativePolicy:
        """Return one shared policy using the fixed treatment assignment and schedule."""

        return NarrativePolicy(
            quantity=quantity,
            narratives=self.narratives_for(treatment),
            exposures=treatment.exposures,
            decision_threshold=decision_threshold,
        )


@dataclass(frozen=True, slots=True)
class NarrativeMarketStabilityOutcome:
    """Aggregate active-window mediator, liquidity, and stability outcomes."""

    treatment_id: str
    assigned_homogeneity: Decimal
    active_period_count: int
    mean_decision_concentration: Decimal | None
    mean_accepted_order_concentration: Decimal | None
    mean_executed_flow_concentration: Decimal | None
    mean_total_depth: Decimal | None
    mean_total_depth_depletion: Decimal | None
    mean_thin_side_depth: Decimal | None
    mean_thin_side_depletion: Decimal | None
    mean_depth_asymmetry: Decimal | None
    mean_relative_spread: Decimal | None
    mean_spread_amplification: Decimal | None
    mid_realized_volatility: float | None
    maximum_drawdown: Decimal | None
    mean_absolute_relative_dislocation: Decimal | None
    treatment_rejected_order_count: int
    treatment_executed_volume: Decimal
    market_trade_volume: Decimal

    def metric_items(
        self,
    ) -> tuple[tuple[str, int | float | Decimal | None], ...]:
        """Return a stable projection for later replicate-level inference."""

        return (
            ("active_period_count", self.active_period_count),
            ("market_trade_volume", self.market_trade_volume),
            ("maximum_drawdown", self.maximum_drawdown),
            (
                "mean_absolute_relative_dislocation",
                self.mean_absolute_relative_dislocation,
            ),
            (
                "mean_accepted_order_concentration",
                self.mean_accepted_order_concentration,
            ),
            ("mean_decision_concentration", self.mean_decision_concentration),
            ("mean_depth_asymmetry", self.mean_depth_asymmetry),
            (
                "mean_executed_flow_concentration",
                self.mean_executed_flow_concentration,
            ),
            ("mean_relative_spread", self.mean_relative_spread),
            ("mean_spread_amplification", self.mean_spread_amplification),
            (
                "mean_thin_side_depletion",
                self.mean_thin_side_depletion,
            ),
            ("mean_thin_side_depth", self.mean_thin_side_depth),
            ("mean_total_depth", self.mean_total_depth),
            (
                "mean_total_depth_depletion",
                self.mean_total_depth_depletion,
            ),
            ("mid_realized_volatility", self.mid_realized_volatility),
            (
                "treatment_executed_volume",
                self.treatment_executed_volume,
            ),
            (
                "treatment_rejected_order_count",
                self.treatment_rejected_order_count,
            ),
        )


def _active_dataset(
    dataset: FinanceResearchDataset,
    treatment: NarrativeHomogeneityTreatment,
) -> FinanceResearchDataset:
    start = treatment.active_from
    end = treatment.active_until

    active = FinanceResearchDataset(
        schema_version=dataset.schema_version,
        participants=dataset.participants,
        decisions=tuple(row for row in dataset.decisions if start <= row.period < end),
        cancellations=tuple(row for row in dataset.cancellations if start <= row.period < end),
        orders=tuple(row for row in dataset.orders if start <= row.period < end),
        trades=tuple(row for row in dataset.trades if start <= row.period < end),
        market_states=tuple(row for row in dataset.market_states if start <= row.period < end),
        accounts=tuple(row for row in dataset.accounts if start <= row.period < end),
        positions=tuple(row for row in dataset.positions if start <= row.period < end),
    )
    active.validate()
    if not active.market_states:
        raise InvalidNarrativeStabilityError(
            "dataset contains no market states inside the treatment active window"
        )
    return active


def _mean_treatment_executed_flow_concentration(
    dataset: FinanceResearchDataset,
    treatment: NarrativeHomogeneityTreatment,
) -> Decimal | None:
    treatment_ids = set(treatment.agent_ids)
    values: list[Decimal] = []
    for period in range(treatment.active_from, treatment.active_until):
        buy = _ZERO
        sell = _ZERO
        for order in dataset.orders:
            if order.period != period or order.agent_id not in treatment_ids:
                continue
            if not order.accepted or order.executed_quantity == _ZERO:
                continue
            if order.side == "buy":
                buy += order.executed_quantity
            elif order.side == "sell":
                sell += order.executed_quantity
            else:
                raise InvalidNarrativeStabilityError(
                    f"unsupported treatment order side {order.side!r}"
                )
        concentration = _quantity_concentration(buy, sell)
        if concentration is not None:
            values.append(concentration)

    if not values:
        return None
    return sum(values, start=_ZERO) / Decimal(len(values))


def evaluate_narrative_market_stability(
    dataset: FinanceResearchDataset,
    treatment: NarrativeHomogeneityTreatment,
    *,
    reference_side_depth: Decimal,
    reference_spread: Decimal,
) -> NarrativeMarketStabilityOutcome:
    """Evaluate downstream outcomes without treating them as software invariants."""

    if not isinstance(dataset, FinanceResearchDataset):
        raise TypeError("dataset must be a FinanceResearchDataset")
    if not isinstance(treatment, NarrativeHomogeneityTreatment):
        raise TypeError("treatment must be a NarrativeHomogeneityTreatment")

    side_reference = _positive_decimal(
        reference_side_depth,
        field_name="reference_side_depth",
    )
    spread_reference = _positive_decimal(
        reference_spread,
        field_name="reference_spread",
    )

    dataset.validate()
    active = _active_dataset(dataset, treatment)
    measurements = tuple(
        item for item in measure_narrative_homogeneity(dataset, treatment) if item.treatment_active
    )
    if len(measurements) != len(active.market_states):
        raise InvalidNarrativeStabilityError(
            "active narrative measurements must align one-to-one with market states"
        )

    treatment_ids = set(treatment.agent_ids)
    treatment_orders = tuple(order for order in active.orders if order.agent_id in treatment_ids)

    reference_total_depth = side_reference * Decimal("2")
    spread_points = relative_spreads(active)
    total_depth_points = total_depth(active)
    total_depletion_points = depth_depletion(
        active,
        reference_depth=reference_total_depth,
    )
    thin_depth_points = thin_side_depth(active)
    thin_depletion_points = thin_side_depletion(
        active,
        reference_side_depth=side_reference,
    )
    asymmetry_points = depth_asymmetry(active)
    amplification_points = spread_amplification(
        active,
        reference_spread=spread_reference,
    )
    dislocation_points = relative_absolute_fundamental_deviation(
        active,
        basis=MarketPriceBasis.MID,
    )

    return NarrativeMarketStabilityOutcome(
        treatment_id=treatment.treatment_id,
        assigned_homogeneity=treatment.assigned_directional_concentration,
        active_period_count=len(active.market_states),
        mean_decision_concentration=_mean_decimal(
            tuple(item.decision_concentration for item in measurements)
        ),
        mean_accepted_order_concentration=_mean_decimal(
            tuple(item.accepted_order_concentration for item in measurements)
        ),
        mean_executed_flow_concentration=(
            _mean_treatment_executed_flow_concentration(active, treatment)
        ),
        mean_total_depth=_mean_decimal(tuple(point.value for point in total_depth_points)),
        mean_total_depth_depletion=_mean_decimal(
            tuple(point.value for point in total_depletion_points)
        ),
        mean_thin_side_depth=_mean_decimal(tuple(point.value for point in thin_depth_points)),
        mean_thin_side_depletion=_mean_decimal(
            tuple(point.value for point in thin_depletion_points)
        ),
        mean_depth_asymmetry=_mean_decimal(tuple(point.value for point in asymmetry_points)),
        mean_relative_spread=_mean_decimal(tuple(point.value for point in spread_points)),
        mean_spread_amplification=_mean_decimal(
            tuple(point.value for point in amplification_points)
        ),
        mid_realized_volatility=realized_volatility(
            active,
            basis=MarketPriceBasis.MID,
        ),
        maximum_drawdown=maximum_drawdown(
            active,
            basis=MarketPriceBasis.MID,
        ),
        mean_absolute_relative_dislocation=_mean_decimal(
            tuple(point.value for point in dislocation_points)
        ),
        treatment_rejected_order_count=sum(not order.accepted for order in treatment_orders),
        treatment_executed_volume=sum(
            (order.executed_quantity for order in treatment_orders),
            start=_ZERO,
        ),
        market_trade_volume=sum(
            (trade.quantity for trade in active.trades),
            start=_ZERO,
        ),
    )


def evaluate_narrative_market_stability_sweep(
    datasets: tuple[FinanceResearchDataset, ...],
    treatments: tuple[NarrativeHomogeneityTreatment, ...],
    *,
    reference_side_depth: Decimal,
    reference_spread: Decimal,
) -> tuple[NarrativeMarketStabilityOutcome, ...]:
    """Evaluate a treatment family while rejecting obvious cross-treatment confounds."""

    if not isinstance(datasets, tuple) or not datasets:
        raise InvalidNarrativeStabilityError("datasets must be a non-empty tuple")
    if not isinstance(treatments, tuple) or not treatments:
        raise InvalidNarrativeStabilityError("treatments must be a non-empty tuple")
    if len(datasets) != len(treatments):
        raise InvalidNarrativeStabilityError("datasets and treatments must have equal length")
    if not all(isinstance(item, FinanceResearchDataset) for item in datasets):
        raise InvalidNarrativeStabilityError("datasets must contain FinanceResearchDataset values")
    if not all(isinstance(item, NarrativeHomogeneityTreatment) for item in treatments):
        raise InvalidNarrativeStabilityError(
            "treatments must contain NarrativeHomogeneityTreatment values"
        )

    first = treatments[0]
    signature = (
        first.agent_ids,
        first.focal_direction,
        first.strength,
        first.confidence,
        first.exposure_weight,
        first.active_from,
        first.active_until,
    )
    for treatment in treatments[1:]:
        candidate = (
            treatment.agent_ids,
            treatment.focal_direction,
            treatment.strength,
            treatment.confidence,
            treatment.exposure_weight,
            treatment.active_from,
            treatment.active_until,
        )
        if candidate != signature:
            raise InvalidNarrativeStabilityError(
                "stability sweep treatments may differ only in homogeneity and treatment_id"
            )

    homogeneities = tuple(item.homogeneity for item in treatments)
    if len(set(homogeneities)) != len(homogeneities):
        raise InvalidNarrativeStabilityError("stability sweep homogeneity values must be unique")

    return tuple(
        evaluate_narrative_market_stability(
            dataset,
            treatment,
            reference_side_depth=reference_side_depth,
            reference_spread=reference_spread,
        )
        for dataset, treatment in zip(datasets, treatments, strict=True)
    )
