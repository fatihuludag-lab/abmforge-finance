"""Deterministic moving-fundamental calibration benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance import (
    Account,
    DeterministicFundamentalPath,
    DynamicPassiveLiquidityPolicy,
    Exchange,
    Instrument,
    MarketClock,
    NoisePolicy,
    Portfolio,
    Side,
    Trader,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.calibration.baseline import CalibrationExperimentResult
from abmforge_finance.calibration.contracts import CalibrationRunSpec, CalibrationScenario
from abmforge_finance.calibration.runner import run_calibration_replicates
from abmforge_finance.calibration.summary import summarize_calibration_runs
from abmforge_finance.exceptions import CalibrationExecutionError, InvalidCalibrationError
from abmforge_finance.recording import FinanceResearchDataset, FinanceResearchRecorder

_ZERO = Decimal("0")


def _positive_decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= _ZERO:
        raise InvalidCalibrationError(f"{field_name} must be a positive finite Decimal")
    return value


@dataclass(frozen=True, slots=True)
class FundamentalTrackingBenchmarkConfig:
    """Explicit deterministic fundamental path for price-tracking validation."""

    fundamental_path: tuple[Decimal, ...]
    tick_size: Decimal = Decimal("1")
    lot_size: Decimal = Decimal("1")
    passive_quantity: Decimal = Decimal("10")
    quote_offset_ticks: int = 1
    noise_trader_count: int = 1
    noise_quantity: Decimal = Decimal("1")
    noise_activity_bps: int = 0
    scenario_id: str = "fundamental-tracking"
    treatment_id: str = "deterministic-path"

    def __post_init__(self) -> None:
        if not isinstance(self.fundamental_path, tuple) or len(self.fundamental_path) < 2:
            raise InvalidCalibrationError(
                "fundamental_path must be a tuple with at least two values"
            )
        for index, value in enumerate(self.fundamental_path):
            _positive_decimal(value, field_name=f"fundamental_path[{index}]")

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
        if (
            isinstance(self.noise_trader_count, bool)
            or not isinstance(self.noise_trader_count, int)
            or self.noise_trader_count < 1
        ):
            raise InvalidCalibrationError("noise_trader_count must be a positive integer")
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
        if passive < noise * Decimal(self.noise_trader_count):
            raise InvalidCalibrationError(
                "passive_quantity must cover worst-case same-side noise demand within one period"
            )
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise InvalidCalibrationError("scenario_id must be a non-empty string")
        if not isinstance(self.treatment_id, str) or not self.treatment_id.strip():
            raise InvalidCalibrationError("treatment_id must be a non-empty string")

        Instrument("CAL", tick, lot)
        DeterministicFundamentalPath(self.fundamental_path)

    @property
    def periods(self) -> int:
        """Return the exact frozen fundamental-path horizon."""

        return len(self.fundamental_path)

    def scenario(self) -> CalibrationScenario:
        """Return canonical seed-independent provenance for the tracking treatment."""

        return CalibrationScenario(
            scenario_id=self.scenario_id,
            treatment_id=self.treatment_id,
            periods=self.periods,
            parameters=(
                (
                    "fundamental_path",
                    ",".join(str(value) for value in self.fundamental_path),
                ),
                ("lot_size", str(self.lot_size)),
                ("noise_activity_bps", str(self.noise_activity_bps)),
                ("noise_quantity", str(self.noise_quantity)),
                ("noise_trader_count", str(self.noise_trader_count)),
                ("passive_quantity", str(self.passive_quantity)),
                ("quote_offset_ticks", str(self.quote_offset_ticks)),
                ("tick_size", str(self.tick_size)),
            ),
        )


class _FundamentalTrackingBenchmarkModel(FinanceABMModel):
    def __init__(
        self,
        *,
        config: FundamentalTrackingBenchmarkConfig,
        seed: int,
    ) -> None:
        self._tracking_config = config
        super().__init__(seed=seed)

    def build_finance_components(self) -> FinanceComponents:
        config = self._tracking_config
        instrument = Instrument("CAL", config.tick_size, config.lot_size)
        exchange = Exchange(instrument)

        per_period_noise = config.noise_quantity * Decimal(config.noise_trader_count)
        horizon_noise = per_period_noise * Decimal(config.periods)
        price_ceiling = max(config.fundamental_path) + config.tick_size * Decimal(
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
            fundamental=DeterministicFundamentalPath(config.fundamental_path),
            traders=tuple(traders),
            research_recorder=FinanceResearchRecorder(),
        )


def _dataset_for_tracking_spec(
    config: FundamentalTrackingBenchmarkConfig,
    spec: CalibrationRunSpec,
) -> FinanceResearchDataset:
    model = _FundamentalTrackingBenchmarkModel(config=config, seed=spec.seed)
    model.setup()
    model.run_for(spec.scenario.periods)
    recorder = model.finance.research_recorder
    if recorder is None:
        raise CalibrationExecutionError(
            "tracking benchmark model did not expose a research recorder"
        )
    return recorder.dataset


def run_fundamental_tracking_benchmark(
    config: FundamentalTrackingBenchmarkConfig,
    *,
    seeds: tuple[int, ...],
) -> CalibrationExperimentResult:
    """Run one frozen moving-fundamental benchmark over explicit replicate seeds."""

    if not isinstance(config, FundamentalTrackingBenchmarkConfig):
        raise TypeError("config must be a FundamentalTrackingBenchmarkConfig")

    scenario = config.scenario()
    runs = run_calibration_replicates(
        scenario,
        seeds=seeds,
        dataset_factory=lambda spec: _dataset_for_tracking_spec(config, spec),
    )
    return CalibrationExperimentResult(
        scenario=scenario,
        runs=runs,
        summary=summarize_calibration_runs(runs),
    )
