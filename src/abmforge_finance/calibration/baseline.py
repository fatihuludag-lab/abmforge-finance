"""Controlled constant-fundamental baseline market ecology."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.agents import Trader
from abmforge_finance.calibration.contracts import CalibrationRunSpec, CalibrationScenario
from abmforge_finance.calibration.result import CalibrationRunResult
from abmforge_finance.calibration.runner import run_calibration_replicates
from abmforge_finance.calibration.summary import (
    CalibrationSummary,
    summarize_calibration_runs,
)
from abmforge_finance.domain import Account, Instrument, Portfolio, Side
from abmforge_finance.exceptions import CalibrationExecutionError, InvalidCalibrationError
from abmforge_finance.market import ConstantFundamentalValue, Exchange, MarketClock
from abmforge_finance.policies import DynamicPassiveLiquidityPolicy, NoisePolicy
from abmforge_finance.recording import FinanceResearchDataset, FinanceResearchRecorder

_ZERO = Decimal("0")


def _positive_decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= _ZERO:
        raise InvalidCalibrationError(f"{field_name} must be a positive finite Decimal")
    return value


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidCalibrationError(f"{field_name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class ConstantFundamentalBenchmarkConfig:
    """Explicit synthetic baseline configuration; not an empirical calibration."""

    periods: int = 20
    fundamental_value: Decimal = Decimal("100")
    tick_size: Decimal = Decimal("1")
    lot_size: Decimal = Decimal("1")
    passive_quantity: Decimal = Decimal("10")
    quote_offset_ticks: int = 1
    noise_trader_count: int = 1
    noise_quantity: Decimal = Decimal("1")
    noise_activity_bps: int = 10_000
    scenario_id: str = "constant-fundamental-baseline"
    treatment_id: str = "baseline"

    def __post_init__(self) -> None:
        _positive_int(self.periods, field_name="periods")
        if self.periods < 2:
            raise InvalidCalibrationError("periods must be at least 2")
        fundamental = _positive_decimal(
            self.fundamental_value,
            field_name="fundamental_value",
        )
        tick = _positive_decimal(self.tick_size, field_name="tick_size")
        lot = _positive_decimal(self.lot_size, field_name="lot_size")
        passive = _positive_decimal(
            self.passive_quantity,
            field_name="passive_quantity",
        )
        noise = _positive_decimal(self.noise_quantity, field_name="noise_quantity")

        if (
            isinstance(self.quote_offset_ticks, bool)
            or not isinstance(self.quote_offset_ticks, int)
            or self.quote_offset_ticks < 1
        ):
            raise InvalidCalibrationError("quote_offset_ticks must be a positive integer")
        _positive_int(self.noise_trader_count, field_name="noise_trader_count")
        if (
            isinstance(self.noise_activity_bps, bool)
            or not isinstance(self.noise_activity_bps, int)
            or self.noise_activity_bps < 0
            or self.noise_activity_bps > 10_000
        ):
            raise InvalidCalibrationError("noise_activity_bps must be an integer in [0, 10000]")
        if passive % lot != _ZERO:
            raise InvalidCalibrationError("passive_quantity must align to lot_size")
        if noise % lot != _ZERO:
            raise InvalidCalibrationError("noise_quantity must align to lot_size")
        worst_period_demand = noise * Decimal(self.noise_trader_count)
        if passive < worst_period_demand:
            raise InvalidCalibrationError(
                "passive_quantity must cover worst-case same-side noise demand within one period"
            )
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise InvalidCalibrationError("scenario_id must be a non-empty string")
        if not isinstance(self.treatment_id, str) or not self.treatment_id.strip():
            raise InvalidCalibrationError("treatment_id must be a non-empty string")

        Instrument("CAL", tick, lot)
        ConstantFundamentalValue(fundamental)

    def scenario(self) -> CalibrationScenario:
        """Return canonical seed-independent provenance for this treatment."""

        return CalibrationScenario(
            scenario_id=self.scenario_id,
            treatment_id=self.treatment_id,
            periods=self.periods,
            parameters=(
                ("fundamental_value", str(self.fundamental_value)),
                ("lot_size", str(self.lot_size)),
                ("noise_activity_bps", str(self.noise_activity_bps)),
                ("noise_quantity", str(self.noise_quantity)),
                ("noise_trader_count", str(self.noise_trader_count)),
                ("passive_quantity", str(self.passive_quantity)),
                ("quote_offset_ticks", str(self.quote_offset_ticks)),
                ("tick_size", str(self.tick_size)),
            ),
        )


@dataclass(frozen=True, slots=True)
class CalibrationExperimentResult:
    """Replicates plus one descriptive summary for a treatment."""

    scenario: CalibrationScenario
    runs: tuple[CalibrationRunResult, ...]
    summary: CalibrationSummary


class _ConstantFundamentalBenchmarkModel(FinanceABMModel):
    def __init__(
        self,
        *,
        config: ConstantFundamentalBenchmarkConfig,
        seed: int,
    ) -> None:
        self._benchmark_config = config
        super().__init__(seed=seed)

    def build_finance_components(self) -> FinanceComponents:
        config = self._benchmark_config
        instrument = Instrument("CAL", config.tick_size, config.lot_size)
        exchange = Exchange(instrument)

        per_period_noise = config.noise_quantity * Decimal(config.noise_trader_count)
        horizon_noise = per_period_noise * Decimal(config.periods)
        price_ceiling = config.fundamental_value + config.tick_size * Decimal(
            config.quote_offset_ticks + 1
        )

        exchange.register(
            Account(
                "lp-bid",
                price_ceiling * (config.passive_quantity + horizon_noise),
            ),
            Portfolio("lp-bid"),
        )
        exchange.register(
            Account("lp-ask", _ZERO),
            Portfolio(
                "lp-ask",
                (("CAL", config.passive_quantity + horizon_noise),),
            ),
        )

        traders: list[Trader] = [
            Trader(
                "lp-bid",
                DynamicPassiveLiquidityPolicy(
                    Side.BUY,
                    config.passive_quantity,
                    config.tick_size,
                    offset_ticks=config.quote_offset_ticks,
                ),
            ),
            Trader(
                "lp-ask",
                DynamicPassiveLiquidityPolicy(
                    Side.SELL,
                    config.passive_quantity,
                    config.tick_size,
                    offset_ticks=config.quote_offset_ticks,
                ),
            ),
        ]

        per_noise_horizon = config.noise_quantity * Decimal(config.periods)
        for index in range(config.noise_trader_count):
            agent_id = f"noise-{index:04d}"
            exchange.register(
                Account(agent_id, price_ceiling * per_noise_horizon),
                Portfolio(agent_id, (("CAL", per_noise_horizon),)),
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
    config: ConstantFundamentalBenchmarkConfig,
    spec: CalibrationRunSpec,
) -> FinanceResearchDataset:
    model = _ConstantFundamentalBenchmarkModel(config=config, seed=spec.seed)
    model.setup()
    model.run_for(spec.scenario.periods)
    recorder = model.finance.research_recorder
    if recorder is None:
        raise CalibrationExecutionError("benchmark model did not expose a research recorder")
    return recorder.dataset


def run_constant_fundamental_benchmark(
    config: ConstantFundamentalBenchmarkConfig,
    *,
    seeds: tuple[int, ...],
) -> CalibrationExperimentResult:
    """Run a controlled constant-fundamental ecology over explicit replicate seeds."""

    if not isinstance(config, ConstantFundamentalBenchmarkConfig):
        raise TypeError("config must be a ConstantFundamentalBenchmarkConfig")
    scenario = config.scenario()
    runs = run_calibration_replicates(
        scenario,
        seeds=seeds,
        dataset_factory=lambda spec: _dataset_for_spec(config, spec),
    )
    return CalibrationExperimentResult(
        scenario=scenario,
        runs=runs,
        summary=summarize_calibration_runs(runs),
    )


def run_passive_depth_sweep(
    config: ConstantFundamentalBenchmarkConfig,
    *,
    passive_quantities: tuple[Decimal, ...],
    seeds: tuple[int, ...],
) -> tuple[CalibrationExperimentResult, ...]:
    """Run common-seed passive-depth treatments without fitting any parameter."""

    if not isinstance(config, ConstantFundamentalBenchmarkConfig):
        raise TypeError("config must be a ConstantFundamentalBenchmarkConfig")
    if not isinstance(passive_quantities, tuple) or not passive_quantities:
        raise InvalidCalibrationError("passive_quantities must be a non-empty tuple")
    if len(set(passive_quantities)) != len(passive_quantities):
        raise InvalidCalibrationError("passive_quantities must be unique")

    experiments: list[CalibrationExperimentResult] = []
    for quantity in passive_quantities:
        _positive_decimal(quantity, field_name="passive_quantity")
        treatment = replace(
            config,
            passive_quantity=quantity,
            treatment_id=f"passive-depth={quantity}",
        )
        experiments.append(
            run_constant_fundamental_benchmark(
                treatment,
                seeds=seeds,
            )
        )
    return tuple(experiments)
