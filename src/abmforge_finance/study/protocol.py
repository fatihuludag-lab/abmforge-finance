"""Prespecified flagship narrative-stability study protocol."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from importlib import resources

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    NarrativeStabilityBenchmarkConfig,
    infer_narrative_stability_sweep,
)
from abmforge_finance.calibration.summary import summarize_calibration_runs
from abmforge_finance.domain import NarrativeDirection
from abmforge_finance.exceptions import StudyProtocolError

_ZERO = Decimal("0")
_ONE = Decimal("1")


class OutcomeRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    MECHANISM = "mechanism"
    DIAGNOSTIC = "diagnostic"


class MultiplicityMethod(str, Enum):
    HOLM = "holm"


@dataclass(frozen=True, slots=True)
class StudyOutcome:
    metric_name: str
    role: OutcomeRole

    def __post_init__(self) -> None:
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise StudyProtocolError("metric_name must be a non-empty string")
        if not isinstance(self.role, OutcomeRole):
            raise StudyProtocolError("role must be an OutcomeRole")


@dataclass(frozen=True, slots=True)
class PrecisionTarget:
    metric_name: str
    max_ci_half_width: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise StudyProtocolError("precision metric_name must be non-empty")
        if (
            not isinstance(self.max_ci_half_width, Decimal)
            or not self.max_ci_half_width.is_finite()
            or self.max_ci_half_width <= _ZERO
        ):
            raise StudyProtocolError("max_ci_half_width must be a positive finite Decimal")


@dataclass(frozen=True, slots=True)
class PrecisionPilotPlan:
    candidate_seed_counts: tuple[int, ...]
    targets: tuple[PrecisionTarget, ...]
    confidence_level: Decimal = Decimal("0.95")

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_seed_counts, tuple) or not self.candidate_seed_counts:
            raise StudyProtocolError("candidate_seed_counts must be non-empty")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 2
            for value in self.candidate_seed_counts
        ):
            raise StudyProtocolError("candidate seed counts must be integers >= 2")
        if tuple(sorted(set(self.candidate_seed_counts))) != self.candidate_seed_counts:
            raise StudyProtocolError("candidate_seed_counts must be strictly increasing and unique")
        if not isinstance(self.targets, tuple) or not self.targets:
            raise StudyProtocolError("precision targets must be non-empty")
        names = tuple(target.metric_name for target in self.targets)
        if len(set(names)) != len(names):
            raise StudyProtocolError("precision target metric names must be unique")
        if (
            not isinstance(self.confidence_level, Decimal)
            or not self.confidence_level.is_finite()
            or self.confidence_level <= _ZERO
            or self.confidence_level >= _ONE
        ):
            raise StudyProtocolError("confidence_level must be in (0, 1)")

    @property
    def maximum_seed_count(self) -> int:
        return self.candidate_seed_counts[-1]


@dataclass(frozen=True, slots=True)
class RobustnessRegime:
    regime_id: str
    parameter_name: str
    parameter_value: str

    def __post_init__(self) -> None:
        allowed = {
            "direction_schedule",
            "noise_activity_bps",
            "noise_trader_count",
            "passive_quantity_per_level",
        }
        if not isinstance(self.regime_id, str) or not self.regime_id.strip():
            raise StudyProtocolError("regime_id must be non-empty")
        if self.parameter_name not in allowed:
            raise StudyProtocolError(f"unsupported robustness parameter {self.parameter_name!r}")
        if not isinstance(self.parameter_value, str) or not self.parameter_value.strip():
            raise StudyProtocolError("parameter_value must be non-empty")


@dataclass(frozen=True, slots=True)
class FlagshipStudyProtocol:
    protocol_id: str
    protocol_version: str
    protocol_status: str
    benchmark_config: NarrativeStabilityBenchmarkConfig
    homogeneities: tuple[Decimal, ...]
    control_homogeneity: Decimal
    outcomes: tuple[StudyOutcome, ...]
    multiplicity_method: MultiplicityMethod
    familywise_alpha: Decimal
    multiplicity_scope: str
    precision_plan: PrecisionPilotPlan
    pilot_seed_namespace: str
    confirmatory_seed_namespace: str
    robustness_regimes: tuple[RobustnessRegime, ...]

    def __post_init__(self) -> None:
        if self.pilot_seed_namespace == self.confirmatory_seed_namespace:
            raise StudyProtocolError("pilot and confirmatory seed namespaces must be distinct")
        if not isinstance(self.benchmark_config, NarrativeStabilityBenchmarkConfig):
            raise StudyProtocolError("benchmark_config has invalid type")
        if tuple(sorted(set(self.homogeneities))) != self.homogeneities:
            raise StudyProtocolError("homogeneities must be strictly increasing and unique")
        if self.homogeneities.count(self.control_homogeneity) != 1:
            raise StudyProtocolError("control_homogeneity must occur exactly once")
        names = tuple(outcome.metric_name for outcome in self.outcomes)
        if len(set(names)) != len(names):
            raise StudyProtocolError("study outcome metric names must be unique")
        if not self.primary_metric_names:
            raise StudyProtocolError("at least one primary outcome is required")
        target_names = {target.metric_name for target in self.precision_plan.targets}
        if target_names != set(self.primary_metric_names):
            raise StudyProtocolError("precision targets must match the primary outcome set exactly")
        if (
            not isinstance(self.familywise_alpha, Decimal)
            or not self.familywise_alpha.is_finite()
            or self.familywise_alpha <= _ZERO
            or self.familywise_alpha >= _ONE
        ):
            raise StudyProtocolError("familywise_alpha must be in (0, 1)")
        regime_ids = tuple(regime.regime_id for regime in self.robustness_regimes)
        if len(set(regime_ids)) != len(regime_ids):
            raise StudyProtocolError("robustness regime IDs must be unique")
        for value in self.homogeneities:
            self.benchmark_config.treatment(value)
        for regime in self.robustness_regimes:
            _apply_regime(self.benchmark_config, regime)

    @property
    def primary_metric_names(self) -> tuple[str, ...]:
        return tuple(item.metric_name for item in self.outcomes if item.role is OutcomeRole.PRIMARY)

    @property
    def primary_hypothesis_count(self) -> int:
        return len(self.primary_metric_names) * (len(self.homogeneities) - 1)

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(),
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json.encode()).hexdigest()

    def to_mapping(self) -> dict[str, object]:
        config = self.benchmark_config
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_status": self.protocol_status,
            "benchmark_family": "narrative-stability-v1",
            "treatment": {
                "control_homogeneity": _decimal_text(self.control_homogeneity),
                "homogeneities": [_decimal_text(value) for value in self.homogeneities],
            },
            "baseline_config": {
                "direction_schedule": [direction.value for direction in config.direction_schedule],
                "fundamental_value": _decimal_text(config.fundamental_value),
                "tick_size": _decimal_text(config.tick_size),
                "lot_size": _decimal_text(config.lot_size),
                "passive_levels": config.passive_levels,
                "passive_quantity_per_level": _decimal_text(config.passive_quantity_per_level),
                "narrative_agent_count": config.narrative_agent_count,
                "narrative_quantity": _decimal_text(config.narrative_quantity),
                "narrative_strength": _decimal_text(config.narrative_strength),
                "narrative_confidence": _decimal_text(config.narrative_confidence),
                "narrative_exposure_weight": _decimal_text(config.narrative_exposure_weight),
                "decision_threshold": _decimal_text(config.decision_threshold),
                "noise_trader_count": config.noise_trader_count,
                "noise_quantity": _decimal_text(config.noise_quantity),
                "noise_activity_bps": config.noise_activity_bps,
                "scenario_id": config.scenario_id,
            },
            "outcomes": [
                {"metric_name": item.metric_name, "role": item.role.value} for item in self.outcomes
            ],
            "multiplicity": {
                "method": self.multiplicity_method.value,
                "familywise_alpha": _decimal_text(self.familywise_alpha),
                "scope": self.multiplicity_scope,
                "primary_hypothesis_count": self.primary_hypothesis_count,
            },
            "precision_pilot": {
                "candidate_seed_counts": list(self.precision_plan.candidate_seed_counts),
                "confidence_level": _decimal_text(self.precision_plan.confidence_level),
                "targets": [
                    {
                        "metric_name": target.metric_name,
                        "max_ci_half_width": _decimal_text(target.max_ci_half_width),
                    }
                    for target in self.precision_plan.targets
                ],
                "selection_rule": ("smallest-candidate-meeting-all-primary-max-half-width-targets"),
                "failure_rule": ("no-confirmatory-run-if-no-candidate-meets-targets"),
            },
            "seed_design": {
                "pilot_namespace": self.pilot_seed_namespace,
                "confirmatory_namespace": self.confirmatory_seed_namespace,
                "reuse_pilot_in_confirmatory": False,
            },
            "robustness_regimes": [
                {
                    "regime_id": regime.regime_id,
                    "parameter_name": regime.parameter_name,
                    "parameter_value": regime.parameter_value,
                }
                for regime in self.robustness_regimes
            ],
        }


@dataclass(frozen=True, slots=True)
class PrecisionMetricCheckpoint:
    metric_name: str
    maximum_half_width: float
    target_half_width: Decimal
    criterion_met: bool


@dataclass(frozen=True, slots=True)
class PrecisionPilotCheckpoint:
    seed_count: int
    metrics: tuple[PrecisionMetricCheckpoint, ...]
    all_targets_met: bool


@dataclass(frozen=True, slots=True)
class PrecisionPilotReport:
    protocol_fingerprint: str
    checkpoints: tuple[PrecisionPilotCheckpoint, ...]
    selected_seed_count: int | None

    @property
    def ready_for_confirmatory_run(self) -> bool:
        return self.selected_seed_count is not None


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _apply_regime(
    config: NarrativeStabilityBenchmarkConfig,
    regime: RobustnessRegime,
) -> NarrativeStabilityBenchmarkConfig:
    if regime.parameter_name == "passive_quantity_per_level":
        return replace(
            config,
            passive_quantity_per_level=Decimal(regime.parameter_value),
        )
    if regime.parameter_name == "noise_activity_bps":
        return replace(config, noise_activity_bps=int(regime.parameter_value))
    if regime.parameter_name == "noise_trader_count":
        return replace(config, noise_trader_count=int(regime.parameter_value))
    if regime.parameter_name == "direction_schedule":
        try:
            directions = tuple(
                NarrativeDirection(value.strip()) for value in regime.parameter_value.split(",")
            )
        except ValueError as exc:
            raise StudyProtocolError("invalid direction_schedule regime") from exc
        return replace(config, direction_schedule=directions)
    raise StudyProtocolError("unsupported robustness parameter")


def apply_robustness_regime(
    protocol: FlagshipStudyProtocol,
    regime_id: str,
) -> NarrativeStabilityBenchmarkConfig:
    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    matches = tuple(
        regime for regime in protocol.robustness_regimes if regime.regime_id == regime_id
    )
    if len(matches) != 1:
        raise StudyProtocolError(f"unknown robustness regime {regime_id!r}")
    return _apply_regime(protocol.benchmark_config, matches[0])


def flagship_narrative_stability_protocol() -> FlagshipStudyProtocol:
    return FlagshipStudyProtocol(
        protocol_id="flagship-narrative-stability-v1",
        protocol_version="1.0.0",
        protocol_status="precision-pilot-prespecified",
        benchmark_config=NarrativeStabilityBenchmarkConfig(),
        homogeneities=(
            Decimal("0"),
            Decimal("0.25"),
            Decimal("0.5"),
            Decimal("0.75"),
            Decimal("1"),
        ),
        control_homogeneity=Decimal("0"),
        outcomes=(
            StudyOutcome("mean_thin_side_depletion", OutcomeRole.PRIMARY),
            StudyOutcome(
                "mean_absolute_relative_dislocation",
                OutcomeRole.PRIMARY,
            ),
            StudyOutcome("mean_depth_asymmetry", OutcomeRole.SECONDARY),
            StudyOutcome("mid_realized_volatility", OutcomeRole.SECONDARY),
            StudyOutcome("maximum_drawdown", OutcomeRole.SECONDARY),
            StudyOutcome(
                "mean_decision_concentration",
                OutcomeRole.MECHANISM,
            ),
            StudyOutcome(
                "mean_accepted_order_concentration",
                OutcomeRole.MECHANISM,
            ),
            StudyOutcome(
                "mean_executed_flow_concentration",
                OutcomeRole.MECHANISM,
            ),
            StudyOutcome(
                "mean_total_depth_depletion",
                OutcomeRole.DIAGNOSTIC,
            ),
            StudyOutcome("mean_relative_spread", OutcomeRole.DIAGNOSTIC),
            StudyOutcome(
                "mean_spread_amplification",
                OutcomeRole.DIAGNOSTIC,
            ),
            StudyOutcome(
                "treatment_rejected_order_count",
                OutcomeRole.DIAGNOSTIC,
            ),
            StudyOutcome(
                "treatment_executed_volume",
                OutcomeRole.DIAGNOSTIC,
            ),
            StudyOutcome("market_trade_volume", OutcomeRole.DIAGNOSTIC),
        ),
        multiplicity_method=MultiplicityMethod.HOLM,
        familywise_alpha=Decimal("0.05"),
        multiplicity_scope="all-primary-metric-treatment-contrasts",
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(10, 20, 40, 80, 160),
            targets=(
                PrecisionTarget(
                    "mean_thin_side_depletion",
                    Decimal("0.02"),
                ),
                PrecisionTarget(
                    "mean_absolute_relative_dislocation",
                    Decimal("0.0025"),
                ),
            ),
        ),
        pilot_seed_namespace="precision-pilot",
        confirmatory_seed_namespace="confirmatory",
        robustness_regimes=(
            RobustnessRegime(
                "liquidity-low",
                "passive_quantity_per_level",
                "3",
            ),
            RobustnessRegime(
                "liquidity-high",
                "passive_quantity_per_level",
                "6",
            ),
            RobustnessRegime(
                "noise-activity-low",
                "noise_activity_bps",
                "2500",
            ),
            RobustnessRegime(
                "noise-activity-high",
                "noise_activity_bps",
                "7500",
            ),
            RobustnessRegime(
                "noise-population-low",
                "noise_trader_count",
                "2",
            ),
            RobustnessRegime(
                "noise-population-high",
                "noise_trader_count",
                "6",
            ),
            RobustnessRegime(
                "schedule-clustered",
                "direction_schedule",
                "bullish,bullish,bearish,bearish",
            ),
            RobustnessRegime(
                "polarity-reversed",
                "direction_schedule",
                "bearish,bullish,bearish,bullish",
            ),
        ),
    )


def bundled_flagship_protocol_mapping() -> dict[str, object]:
    path = resources.files("abmforge_finance.study").joinpath(
        "specs/flagship_narrative_stability_v1.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StudyProtocolError("bundled protocol JSON must be an object")
    return value


def study_seed_tuple(
    protocol: FlagshipStudyProtocol,
    *,
    namespace: str,
    count: int,
) -> tuple[int, ...]:
    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if not isinstance(namespace, str) or not namespace.strip():
        raise StudyProtocolError("seed namespace must be non-empty")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise StudyProtocolError("seed count must be a positive integer")
    seeds = tuple(
        int.from_bytes(
            hashlib.sha256(
                (f"{protocol.fingerprint}:{namespace.strip()}:{index:08d}").encode()
            ).digest()[:8],
            "big",
        )
        for index in range(count)
    )
    if len(set(seeds)) != len(seeds):
        raise StudyProtocolError("study seed derivation produced a duplicate")
    return seeds


def precision_pilot_seed_tuple(
    protocol: FlagshipStudyProtocol,
) -> tuple[int, ...]:
    return study_seed_tuple(
        protocol,
        namespace=protocol.pilot_seed_namespace,
        count=protocol.precision_plan.maximum_seed_count,
    )


def confirmatory_seed_tuple(
    protocol: FlagshipStudyProtocol,
    selected_seed_count: int,
) -> tuple[int, ...]:
    if selected_seed_count not in protocol.precision_plan.candidate_seed_counts:
        raise StudyProtocolError("selected_seed_count must be a prespecified candidate")
    seeds = study_seed_tuple(
        protocol,
        namespace=protocol.confirmatory_seed_namespace,
        count=selected_seed_count,
    )
    if set(precision_pilot_seed_tuple(protocol)).intersection(seeds):
        raise StudyProtocolError("pilot and confirmatory seeds must be disjoint")
    return seeds


def _prefix(
    experiment: CalibrationExperimentResult,
    count: int,
) -> CalibrationExperimentResult:
    runs = experiment.runs[:count]
    if len(runs) != count:
        raise StudyProtocolError("precision experiment has too few runs")
    return CalibrationExperimentResult(
        scenario=experiment.scenario,
        runs=runs,
        summary=summarize_calibration_runs(runs),
    )


def evaluate_precision_pilot(
    protocol: FlagshipStudyProtocol,
    experiments: tuple[CalibrationExperimentResult, ...],
) -> PrecisionPilotReport:
    if not isinstance(protocol, FlagshipStudyProtocol):
        raise TypeError("protocol must be a FlagshipStudyProtocol")
    if len(experiments) != len(protocol.homogeneities):
        raise StudyProtocolError("precision experiments must match the treatment grid")

    expected_seeds = precision_pilot_seed_tuple(protocol)
    observed_h: list[Decimal] = []
    for experiment in experiments:
        params = dict(experiment.scenario.parameters)
        observed_h.append(Decimal(params["homogeneity"]))
        if tuple(run.spec.seed for run in experiment.runs) != expected_seeds:
            raise StudyProtocolError("precision experiments must use the full pilot seed tuple")
    if tuple(observed_h) != protocol.homogeneities:
        raise StudyProtocolError("precision experiment homogeneities must match protocol order")

    target_by_name = {target.metric_name: target for target in protocol.precision_plan.targets}
    checkpoints: list[PrecisionPilotCheckpoint] = []
    selected: int | None = None

    for count in protocol.precision_plan.candidate_seed_counts:
        prefix = tuple(_prefix(experiment, count) for experiment in experiments)
        inference = infer_narrative_stability_sweep(
            prefix,
            metric_names=protocol.primary_metric_names,
            control_homogeneity=protocol.control_homogeneity,
            confidence_level=float(protocol.precision_plan.confidence_level),
        )
        metric_rows: list[PrecisionMetricCheckpoint] = []
        for metric in inference:
            half_widths = tuple(
                (contrast.confidence_interval_upper - contrast.confidence_interval_lower) / 2.0
                for contrast in metric.contrasts
            )
            maximum = max(half_widths)
            if not math.isfinite(maximum) or maximum < 0.0:
                raise StudyProtocolError("invalid precision CI half-width")
            target = target_by_name[metric.metric_name]
            metric_rows.append(
                PrecisionMetricCheckpoint(
                    metric_name=metric.metric_name,
                    maximum_half_width=maximum,
                    target_half_width=target.max_ci_half_width,
                    criterion_met=maximum <= float(target.max_ci_half_width),
                )
            )
        all_met = all(row.criterion_met for row in metric_rows)
        checkpoints.append(
            PrecisionPilotCheckpoint(
                seed_count=count,
                metrics=tuple(metric_rows),
                all_targets_met=all_met,
            )
        )
        if selected is None and all_met:
            selected = count

    return PrecisionPilotReport(
        protocol_fingerprint=protocol.fingerprint,
        checkpoints=tuple(checkpoints),
        selected_seed_count=selected,
    )
