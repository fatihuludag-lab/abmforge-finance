"""Multi-seed narrative-stability benchmark and paired inference bridge."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.agents import Trader
from abmforge_finance.calibration.baseline import CalibrationExperimentResult
from abmforge_finance.calibration.contracts import (
    CalibrationRunSpec,
    CalibrationScenario,
    validate_seed_tuple,
)
from abmforge_finance.calibration.inference import (
    ContrastRegionSummary,
    PairedTreatmentContrast,
    paired_treatment_contrast,
    summarize_contrast_region,
)
from abmforge_finance.calibration.result import (
    CalibrationRunResult,
    evaluate_calibration_dataset,
)
from abmforge_finance.calibration.summary import summarize_calibration_runs
from abmforge_finance.domain import (
    Account,
    Instrument,
    NarrativeDirection,
    Portfolio,
    Side,
)
from abmforge_finance.exceptions import (
    CalibrationExecutionError,
    CalibrationInferenceError,
    InvalidCalibrationError,
)
from abmforge_finance.experiments import (
    NarrativeDirectionSchedule,
    NarrativeHomogeneityTreatment,
    evaluate_narrative_market_stability,
)
from abmforge_finance.market import ConstantFundamentalValue, Exchange, MarketClock
from abmforge_finance.policies import DynamicPassiveLiquidityPolicy, NoisePolicy
from abmforge_finance.recording import FinanceResearchDataset, FinanceResearchRecorder

_ZERO = Decimal("0")
_ONE = Decimal("1")
_BENCHMARK_FAMILY = "narrative-stability-v1"


def _positive_decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= _ZERO:
        raise InvalidCalibrationError(f"{field_name} must be a positive finite Decimal")
    return value


def _unit_decimal(
    value: object,
    *,
    field_name: str,
    positive: bool = False,
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise InvalidCalibrationError(f"{field_name} must be a finite Decimal")
    if value < _ZERO or value > _ONE or (positive and value == _ZERO):
        interval = "(0, 1]" if positive else "[0, 1]"
        raise InvalidCalibrationError(f"{field_name} must be in {interval}")
    return value


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidCalibrationError(f"{field_name} must be a positive integer")
    return value


def _decimal_label(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


@dataclass(frozen=True, slots=True)
class NarrativeStabilityBenchmarkConfig:
    """Controlled stochastic background for narrative-homogeneity inference."""

    direction_schedule: tuple[NarrativeDirection, ...] = (
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
    )
    fundamental_value: Decimal = Decimal("100")
    tick_size: Decimal = Decimal("1")
    lot_size: Decimal = Decimal("1")
    passive_levels: int = 5
    passive_quantity_per_level: Decimal = Decimal("4")
    narrative_agent_count: int = 8
    narrative_quantity: Decimal = Decimal("1")
    narrative_strength: Decimal = Decimal("1")
    narrative_confidence: Decimal = Decimal("1")
    narrative_exposure_weight: Decimal = Decimal("1")
    decision_threshold: Decimal = Decimal("0")
    noise_trader_count: int = 4
    noise_quantity: Decimal = Decimal("1")
    noise_activity_bps: int = 5_000
    scenario_id: str = "narrative-stability"

    def __post_init__(self) -> None:
        if not isinstance(self.direction_schedule, tuple) or len(self.direction_schedule) < 2:
            raise InvalidCalibrationError(
                "direction_schedule must be a tuple with at least two directions"
            )
        if not all(
            isinstance(direction, NarrativeDirection)
            and direction is not NarrativeDirection.NEUTRAL
            for direction in self.direction_schedule
        ):
            raise InvalidCalibrationError(
                "direction_schedule must contain only BULLISH or BEARISH values"
            )

        fundamental = _positive_decimal(
            self.fundamental_value,
            field_name="fundamental_value",
        )
        tick = _positive_decimal(self.tick_size, field_name="tick_size")
        lot = _positive_decimal(self.lot_size, field_name="lot_size")
        passive = _positive_decimal(
            self.passive_quantity_per_level,
            field_name="passive_quantity_per_level",
        )
        narrative_quantity = _positive_decimal(
            self.narrative_quantity,
            field_name="narrative_quantity",
        )
        noise_quantity = _positive_decimal(
            self.noise_quantity,
            field_name="noise_quantity",
        )

        levels = _positive_int(self.passive_levels, field_name="passive_levels")
        if levels < 2:
            raise InvalidCalibrationError("passive_levels must be at least 2")

        narrative_count = _positive_int(
            self.narrative_agent_count,
            field_name="narrative_agent_count",
        )
        if narrative_count < 2 or narrative_count % 2 != 0:
            raise InvalidCalibrationError(
                "narrative_agent_count must be an even integer of at least 2"
            )

        noise_count = _positive_int(
            self.noise_trader_count,
            field_name="noise_trader_count",
        )
        if (
            isinstance(self.noise_activity_bps, bool)
            or not isinstance(self.noise_activity_bps, int)
            or self.noise_activity_bps < 1
            or self.noise_activity_bps > 10_000
        ):
            raise InvalidCalibrationError("noise_activity_bps must be an integer in [1, 10000]")

        strength = _unit_decimal(
            self.narrative_strength,
            field_name="narrative_strength",
            positive=True,
        )
        confidence = _unit_decimal(
            self.narrative_confidence,
            field_name="narrative_confidence",
            positive=True,
        )
        exposure = _unit_decimal(
            self.narrative_exposure_weight,
            field_name="narrative_exposure_weight",
            positive=True,
        )
        if (
            not isinstance(self.decision_threshold, Decimal)
            or not self.decision_threshold.is_finite()
            or self.decision_threshold < _ZERO
        ):
            raise InvalidCalibrationError(
                "decision_threshold must be a non-negative finite Decimal"
            )
        signal_magnitude = strength * confidence * exposure
        if self.decision_threshold >= signal_magnitude:
            raise InvalidCalibrationError(
                "decision_threshold must remain below the active narrative signal magnitude"
            )

        for quantity, label in (
            (passive, "passive_quantity_per_level"),
            (narrative_quantity, "narrative_quantity"),
            (noise_quantity, "noise_quantity"),
        ):
            if quantity % lot != _ZERO:
                raise InvalidCalibrationError(f"{label} must align to lot_size")

        if fundamental % tick != _ZERO:
            raise InvalidCalibrationError("fundamental_value must align exactly to tick_size")
        if fundamental <= tick * Decimal(levels):
            raise InvalidCalibrationError(
                "fundamental_value must keep every passive bid level strictly positive"
            )

        side_capacity = passive * Decimal(levels)
        worst_same_side_demand = narrative_quantity * Decimal(
            narrative_count
        ) + noise_quantity * Decimal(noise_count)
        if side_capacity <= worst_same_side_demand:
            raise InvalidCalibrationError(
                "passive side capacity must strictly exceed worst-case same-side "
                "narrative plus noise demand"
            )

        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise InvalidCalibrationError("scenario_id must be a non-empty string")

    @property
    def periods(self) -> int:
        return len(self.direction_schedule)

    @property
    def narrative_agent_ids(self) -> tuple[str, ...]:
        return tuple(f"narrative-{index:04d}" for index in range(self.narrative_agent_count))

    @property
    def reference_side_depth(self) -> Decimal:
        return self.passive_quantity_per_level * Decimal(self.passive_levels)

    @property
    def reference_spread(self) -> Decimal:
        return self.tick_size * Decimal("2")

    def treatment(
        self,
        homogeneity: Decimal,
    ) -> NarrativeHomogeneityTreatment:
        if not isinstance(homogeneity, Decimal):
            raise InvalidCalibrationError("homogeneity must be a Decimal")
        label = _decimal_label(homogeneity)
        return NarrativeHomogeneityTreatment(
            treatment_id=f"narrative-homogeneity={label}",
            agent_ids=self.narrative_agent_ids,
            homogeneity=homogeneity,
            focal_direction=self.direction_schedule[0],
            strength=self.narrative_strength,
            confidence=self.narrative_confidence,
            exposure_weight=self.narrative_exposure_weight,
            active_from=0,
            active_until=self.periods,
        )

    def scenario(self, homogeneity: Decimal) -> CalibrationScenario:
        treatment = self.treatment(homogeneity)
        return CalibrationScenario(
            scenario_id=self.scenario_id,
            treatment_id=treatment.treatment_id,
            periods=self.periods,
            parameters=(
                ("benchmark_family", _BENCHMARK_FAMILY),
                ("decision_threshold", str(self.decision_threshold)),
                (
                    "direction_schedule",
                    ",".join(direction.value for direction in self.direction_schedule),
                ),
                ("fundamental_value", str(self.fundamental_value)),
                ("homogeneity", _decimal_label(homogeneity)),
                ("lot_size", str(self.lot_size)),
                ("narrative_agent_count", str(self.narrative_agent_count)),
                ("narrative_confidence", str(self.narrative_confidence)),
                (
                    "narrative_exposure_weight",
                    str(self.narrative_exposure_weight),
                ),
                ("narrative_quantity", str(self.narrative_quantity)),
                ("narrative_strength", str(self.narrative_strength)),
                ("noise_activity_bps", str(self.noise_activity_bps)),
                ("noise_quantity", str(self.noise_quantity)),
                ("noise_trader_count", str(self.noise_trader_count)),
                ("passive_levels", str(self.passive_levels)),
                (
                    "passive_quantity_per_level",
                    str(self.passive_quantity_per_level),
                ),
                ("tick_size", str(self.tick_size)),
            ),
        )


@dataclass(frozen=True, slots=True)
class NarrativeStabilityRunResult(CalibrationRunResult):
    """One replicate with narrative-specific mediator and liquidity outcomes."""

    assigned_homogeneity: Decimal
    mean_decision_concentration: Decimal | None
    mean_accepted_order_concentration: Decimal | None
    mean_executed_flow_concentration: Decimal | None
    mean_total_depth_depletion: Decimal | None
    mean_thin_side_depth: Decimal | None
    mean_thin_side_depletion: Decimal | None
    mean_depth_asymmetry: Decimal | None
    mean_spread_amplification: Decimal | None
    treatment_rejected_order_count: int
    treatment_executed_volume: Decimal
    market_trade_volume: Decimal

    def metric_items(
        self,
    ) -> tuple[tuple[str, int | float | Decimal | None], ...]:
        metrics = dict(CalibrationRunResult.metric_items(self))
        metrics.update(
            {
                "market_trade_volume": self.market_trade_volume,
                "mean_accepted_order_concentration": (self.mean_accepted_order_concentration),
                "mean_decision_concentration": self.mean_decision_concentration,
                "mean_depth_asymmetry": self.mean_depth_asymmetry,
                "mean_executed_flow_concentration": (self.mean_executed_flow_concentration),
                "mean_spread_amplification": self.mean_spread_amplification,
                "mean_thin_side_depletion": self.mean_thin_side_depletion,
                "mean_thin_side_depth": self.mean_thin_side_depth,
                "mean_total_depth_depletion": self.mean_total_depth_depletion,
                "treatment_executed_volume": self.treatment_executed_volume,
                "treatment_rejected_order_count": (self.treatment_rejected_order_count),
            }
        )
        return tuple(sorted(metrics.items()))


@dataclass(frozen=True, slots=True)
class NarrativeStabilityMetricInference:
    """Paired treatment region for one explicitly selected outcome metric."""

    metric_name: str
    control_homogeneity: Decimal
    contrasts: tuple[PairedTreatmentContrast, ...]
    region: ContrastRegionSummary


class _NarrativeStabilityBenchmarkModel(FinanceABMModel):
    def __init__(
        self,
        *,
        config: NarrativeStabilityBenchmarkConfig,
        treatment: NarrativeHomogeneityTreatment,
        seed: int,
    ) -> None:
        self._benchmark_config = config
        self._treatment = treatment
        super().__init__(seed=seed)

    def build_finance_components(self) -> FinanceComponents:
        config = self._benchmark_config
        instrument = Instrument("NAR", config.tick_size, config.lot_size)
        exchange = Exchange(instrument)
        traders: list[Trader] = []

        price_ceiling = config.fundamental_value + config.tick_size * Decimal(
            config.passive_levels + 1
        )
        passive_horizon = config.passive_quantity_per_level * Decimal(config.periods)

        for offset in range(1, config.passive_levels + 1):
            bid_id = f"lp-bid-{offset:02d}"
            ask_id = f"lp-ask-{offset:02d}"
            exchange.register(
                Account(bid_id, price_ceiling * passive_horizon),
                Portfolio(bid_id),
            )
            exchange.register(
                Account(ask_id, _ZERO),
                Portfolio(ask_id, (("NAR", passive_horizon),)),
            )
            traders.extend(
                (
                    Trader(
                        bid_id,
                        DynamicPassiveLiquidityPolicy(
                            Side.BUY,
                            config.passive_quantity_per_level,
                            config.tick_size,
                            offset_ticks=offset,
                        ),
                    ),
                    Trader(
                        ask_id,
                        DynamicPassiveLiquidityPolicy(
                            Side.SELL,
                            config.passive_quantity_per_level,
                            config.tick_size,
                            offset_ticks=offset,
                        ),
                    ),
                )
            )

        schedule = NarrativeDirectionSchedule(config.direction_schedule)
        narrative_policy = schedule.policy_for(
            self._treatment,
            quantity=config.narrative_quantity,
            decision_threshold=config.decision_threshold,
        )
        narrative_horizon = config.narrative_quantity * Decimal(config.periods)
        for agent_id in self._treatment.agent_ids:
            exchange.register(
                Account(agent_id, price_ceiling * narrative_horizon),
                Portfolio(agent_id, (("NAR", narrative_horizon),)),
            )
            traders.append(Trader(agent_id, narrative_policy))

        noise_horizon = config.noise_quantity * Decimal(config.periods)
        for index in range(config.noise_trader_count):
            agent_id = f"noise-{index:04d}"
            exchange.register(
                Account(agent_id, price_ceiling * noise_horizon),
                Portfolio(agent_id, (("NAR", noise_horizon),)),
            )
            traders.append(
                Trader(
                    agent_id,
                    NoisePolicy(
                        config.noise_quantity,
                        seed=self.finance_seed(f"noise-policy:{index:04d}"),
                        activity_bps=config.noise_activity_bps,
                    ),
                )
            )

        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(config.fundamental_value),
            traders=tuple(traders),
            research_recorder=FinanceResearchRecorder(),
        )


def _dataset_for_spec(
    config: NarrativeStabilityBenchmarkConfig,
    treatment: NarrativeHomogeneityTreatment,
    spec: CalibrationRunSpec,
) -> FinanceResearchDataset:
    model = _NarrativeStabilityBenchmarkModel(
        config=config,
        treatment=treatment,
        seed=spec.seed,
    )
    model.setup()
    model.run_for(spec.scenario.periods)
    recorder = model.finance.research_recorder
    if recorder is None:
        raise CalibrationExecutionError(
            "narrative stability benchmark did not expose a research recorder"
        )
    return recorder.dataset


def evaluate_narrative_stability_run(
    spec: CalibrationRunSpec,
    dataset: FinanceResearchDataset,
    treatment: NarrativeHomogeneityTreatment,
    *,
    reference_side_depth: Decimal,
    reference_spread: Decimal,
) -> NarrativeStabilityRunResult:
    """Evaluate one narrative-stability replicate using the Phase 10C.1 contract."""

    if not isinstance(spec, CalibrationRunSpec):
        raise TypeError("spec must be a CalibrationRunSpec")
    if not isinstance(dataset, FinanceResearchDataset):
        raise TypeError("dataset must be a FinanceResearchDataset")
    if not isinstance(treatment, NarrativeHomogeneityTreatment):
        raise TypeError("treatment must be a NarrativeHomogeneityTreatment")

    parameters = dict(spec.scenario.parameters)
    if parameters.get("benchmark_family") != _BENCHMARK_FAMILY:
        raise InvalidCalibrationError("scenario is not a narrative-stability benchmark scenario")
    try:
        scenario_homogeneity = Decimal(parameters["homogeneity"])
    except (KeyError, ArithmeticError) as exc:
        raise InvalidCalibrationError("scenario must expose a valid homogeneity parameter") from exc
    if scenario_homogeneity != treatment.assigned_directional_concentration:
        raise InvalidCalibrationError("scenario homogeneity does not match the narrative treatment")
    if treatment.active_from != 0 or treatment.active_until != spec.scenario.periods:
        raise InvalidCalibrationError(
            "narrative treatment active window must match the full scenario horizon"
        )

    base = evaluate_calibration_dataset(spec, dataset)
    outcome = evaluate_narrative_market_stability(
        dataset,
        treatment,
        reference_side_depth=reference_side_depth,
        reference_spread=reference_spread,
    )
    return NarrativeStabilityRunResult(
        spec=base.spec,
        dataset_schema_version=base.dataset_schema_version,
        participant_count=base.participant_count,
        decision_count=base.decision_count,
        cancellation_count=base.cancellation_count,
        order_count=base.order_count,
        rejected_order_count=base.rejected_order_count,
        trade_count=base.trade_count,
        trade_volume=base.trade_volume,
        mid_realized_volatility=base.mid_realized_volatility,
        last_trade_realized_volatility=base.last_trade_realized_volatility,
        maximum_drawdown=base.maximum_drawdown,
        mean_relative_spread=base.mean_relative_spread,
        mean_total_depth=base.mean_total_depth,
        mean_absolute_relative_dislocation=(base.mean_absolute_relative_dislocation),
        mean_decision_sign_concentration=(base.mean_decision_sign_concentration),
        assigned_homogeneity=outcome.assigned_homogeneity,
        mean_decision_concentration=outcome.mean_decision_concentration,
        mean_accepted_order_concentration=(outcome.mean_accepted_order_concentration),
        mean_executed_flow_concentration=(outcome.mean_executed_flow_concentration),
        mean_total_depth_depletion=outcome.mean_total_depth_depletion,
        mean_thin_side_depth=outcome.mean_thin_side_depth,
        mean_thin_side_depletion=outcome.mean_thin_side_depletion,
        mean_depth_asymmetry=outcome.mean_depth_asymmetry,
        mean_spread_amplification=outcome.mean_spread_amplification,
        treatment_rejected_order_count=(outcome.treatment_rejected_order_count),
        treatment_executed_volume=outcome.treatment_executed_volume,
        market_trade_volume=outcome.market_trade_volume,
    )


def run_narrative_stability_benchmark(
    config: NarrativeStabilityBenchmarkConfig,
    *,
    homogeneity: Decimal,
    seeds: tuple[int, ...],
) -> CalibrationExperimentResult:
    """Run one homogeneity treatment over an explicit ordered seed tuple."""

    if not isinstance(config, NarrativeStabilityBenchmarkConfig):
        raise TypeError("config must be a NarrativeStabilityBenchmarkConfig")
    validated_seeds = validate_seed_tuple(seeds)
    treatment = config.treatment(homogeneity)
    scenario = config.scenario(homogeneity)

    runs: list[NarrativeStabilityRunResult] = []
    for replicate, seed in enumerate(validated_seeds):
        spec = CalibrationRunSpec(scenario, replicate, seed)
        dataset = _dataset_for_spec(config, treatment, spec)
        runs.append(
            evaluate_narrative_stability_run(
                spec,
                dataset,
                treatment,
                reference_side_depth=config.reference_side_depth,
                reference_spread=config.reference_spread,
            )
        )

    run_tuple = tuple(runs)
    return CalibrationExperimentResult(
        scenario=scenario,
        runs=run_tuple,
        summary=summarize_calibration_runs(run_tuple),
    )


def run_narrative_stability_homogeneity_sweep(
    config: NarrativeStabilityBenchmarkConfig,
    *,
    homogeneities: tuple[Decimal, ...],
    seeds: tuple[int, ...],
) -> tuple[CalibrationExperimentResult, ...]:
    """Run a common-seed homogeneity family with all non-H controls frozen."""

    if not isinstance(config, NarrativeStabilityBenchmarkConfig):
        raise TypeError("config must be a NarrativeStabilityBenchmarkConfig")
    if not isinstance(homogeneities, tuple) or not homogeneities:
        raise InvalidCalibrationError("homogeneities must be a non-empty tuple")
    if len(set(homogeneities)) != len(homogeneities):
        raise InvalidCalibrationError("homogeneities must be unique")

    validated_seeds = validate_seed_tuple(seeds)
    return tuple(
        run_narrative_stability_benchmark(
            config,
            homogeneity=homogeneity,
            seeds=validated_seeds,
        )
        for homogeneity in homogeneities
    )


def _experiment_homogeneity(
    experiment: CalibrationExperimentResult,
) -> Decimal:
    if not isinstance(experiment, CalibrationExperimentResult):
        raise TypeError("experiment must be a CalibrationExperimentResult")
    parameters = dict(experiment.scenario.parameters)
    if parameters.get("benchmark_family") != _BENCHMARK_FAMILY:
        raise CalibrationInferenceError(
            "experiment is not from the narrative-stability benchmark family"
        )
    try:
        value = Decimal(parameters["homogeneity"])
    except (KeyError, ArithmeticError) as exc:
        raise CalibrationInferenceError(
            "narrative-stability experiment must expose homogeneity"
        ) from exc
    if not value.is_finite() or value < _ZERO or value > _ONE:
        raise CalibrationInferenceError(
            "narrative-stability homogeneity must be finite and in [0, 1]"
        )
    return value


def infer_narrative_stability_sweep(
    experiments: tuple[CalibrationExperimentResult, ...],
    *,
    metric_names: tuple[str, ...],
    control_homogeneity: Decimal = Decimal("0"),
    confidence_level: float = 0.95,
) -> tuple[NarrativeStabilityMetricInference, ...]:
    """Reuse Phase 9C.3 paired inference for selected narrative outcomes."""

    if not isinstance(experiments, tuple) or len(experiments) < 2:
        raise CalibrationInferenceError("experiments must contain at least two treatments")
    if not all(isinstance(experiment, CalibrationExperimentResult) for experiment in experiments):
        raise CalibrationInferenceError(
            "experiments must contain CalibrationExperimentResult values"
        )
    if not isinstance(metric_names, tuple) or not metric_names:
        raise CalibrationInferenceError("metric_names must be a non-empty tuple")
    normalized_metrics = tuple(
        metric.strip() for metric in metric_names if isinstance(metric, str) and metric.strip()
    )
    if len(normalized_metrics) != len(metric_names):
        raise CalibrationInferenceError("metric_names must contain only non-empty strings")
    if len(set(normalized_metrics)) != len(normalized_metrics):
        raise CalibrationInferenceError("metric_names must be unique")
    if (
        not isinstance(control_homogeneity, Decimal)
        or not control_homogeneity.is_finite()
        or control_homogeneity < _ZERO
        or control_homogeneity > _ONE
    ):
        raise CalibrationInferenceError("control_homogeneity must be a finite Decimal in [0, 1]")

    homogeneities = tuple(_experiment_homogeneity(experiment) for experiment in experiments)
    control_indices = tuple(
        index for index, value in enumerate(homogeneities) if value == control_homogeneity
    )
    if len(control_indices) != 1:
        raise CalibrationInferenceError("exactly one experiment must match control_homogeneity")

    control_index = control_indices[0]
    control = experiments[control_index]
    treatments = tuple(
        experiment for index, experiment in enumerate(experiments) if index != control_index
    )

    output: list[NarrativeStabilityMetricInference] = []
    for metric_name in normalized_metrics:
        contrasts = tuple(
            paired_treatment_contrast(
                control,
                treatment,
                metric_name=metric_name,
                confidence_level=confidence_level,
            )
            for treatment in treatments
        )
        if any(
            tuple(parameter for parameter, _, _ in contrast.changed_parameters) != ("homogeneity",)
            for contrast in contrasts
        ):
            raise CalibrationInferenceError(
                "narrative stability inference requires homogeneity to be "
                "the only changed scenario parameter"
            )
        output.append(
            NarrativeStabilityMetricInference(
                metric_name=metric_name,
                control_homogeneity=control_homogeneity,
                contrasts=contrasts,
                region=summarize_contrast_region(contrasts),
            )
        )
    return tuple(output)
