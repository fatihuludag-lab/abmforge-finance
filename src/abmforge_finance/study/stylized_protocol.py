"""Prespecified external-validity contract for stylized-fact validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from importlib import resources

from abmforge_finance.calibration import NarrativeStabilityBenchmarkConfig
from abmforge_finance.domain import NarrativeDirection
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study.protocol import flagship_narrative_stability_protocol

_ZERO = Decimal("0")
_ONE = Decimal("1")
_SOURCE_FLAGSHIP_PROTOCOL_FINGERPRINT = (
    "483fbae4791b5f30b88bb036a994db411ce16f39a4fbd12a580679975a28c54b"
)
_INFERENCE_SCOPE = "descriptive-external-validity-no-new-confirmatory-family"
_ESTIMATOR_LOCK = "same-estimator-implementation-for-simulation-and-empirical-data"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class StylizedFactRole(str, Enum):
    """Interpretive role of one prespecified stylized-fact signature."""

    PRIMARY = "primary"
    DIAGNOSTIC = "diagnostic"


class ConcordanceClass(str, Enum):
    """Prespecified simulation-to-empirical comparison classification."""

    CONCORDANT = "concordant"
    DIRECTION_ONLY = "direction-only"
    DISCORDANT = "discordant"
    UNINFORMATIVE = "uninformative"


class StylizedFactExpectation(str, Enum):
    """Qualitative property fixed before validation execution."""

    WEAK_RETURN_AUTOCORRELATION = "weak-short-lag-return-autocorrelation"
    HEAVIER_THAN_GAUSSIAN = "heavier-than-gaussian-reference"
    POSITIVE_VOLATILITY_PERSISTENCE = "positive-volatility-persistence"
    POSITIVE_AGGRESSOR_FLOW_PRICE_IMPACT = "positive-aggressor-flow-price-impact"
    STRONGER_IMPACT_AT_LOW_DEPTH = "stronger-absolute-impact-at-low-depth"
    LIQUIDITY_FRAGILITY = "low-depth-and-depletion-associated-with-larger-price-moves"
    POSITIVE_ORDER_SIGN_PERSISTENCE = "positive-order-sign-persistence"


def _non_empty(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StudyProtocolError(f"{field_name} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StudyProtocolError(f"{field_name} must be a positive integer")
    return value


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


@dataclass(frozen=True, slots=True)
class StylizedFactSpec:
    """One frozen signature definition shared by simulation and empirical data."""

    fact_id: str
    name: str
    role: StylizedFactRole
    estimator_id: str
    expected_relation: StylizedFactExpectation
    parameters: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        fact_id = _non_empty(self.fact_id, field_name="fact_id")
        if re.fullmatch(r"SF-\d{2}", fact_id) is None:
            raise StudyProtocolError("fact_id must match the SF-XX format")
        _non_empty(self.name, field_name="name")
        if not isinstance(self.role, StylizedFactRole):
            raise StudyProtocolError("role must be a StylizedFactRole")
        _non_empty(self.estimator_id, field_name="estimator_id")
        if not isinstance(self.expected_relation, StylizedFactExpectation):
            raise StudyProtocolError("expected_relation must be a StylizedFactExpectation")
        if not isinstance(self.parameters, tuple) or not self.parameters:
            raise StudyProtocolError("parameters must be a non-empty tuple")
        keys: list[str] = []
        for item in self.parameters:
            if not isinstance(item, tuple) or len(item) != 2:
                raise StudyProtocolError("stylized-fact parameters must contain key/value pairs")
            key, value = item
            keys.append(_non_empty(key, field_name="parameter key"))
            _non_empty(value, field_name="parameter value")
        if len(set(keys)) != len(keys):
            raise StudyProtocolError("stylized-fact parameter keys must be unique")

    def to_mapping(self) -> dict[str, object]:
        return {
            "fact_id": self.fact_id,
            "name": self.name,
            "role": self.role.value,
            "estimator_id": self.estimator_id,
            "expected_relation": self.expected_relation.value,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class StylizedValidationProtocol:
    """Frozen Phase 11 external-validity design.

    This protocol is separate from the flagship confirmatory family. It fixes
    simulation horizon, baseline lineage, estimators, qualitative expectations,
    empirical comparison bands, and the no-calibration boundary before the
    validation run exists.
    """

    protocol_id: str
    protocol_version: str
    protocol_status: str
    purpose: str
    source_flagship_protocol_fingerprint: str
    source_benchmark_family: str
    validation_homogeneity: Decimal
    direction_cycle: tuple[NarrativeDirection, ...]
    burn_in_periods: int
    analysis_horizon: int
    replicate_count: int
    maximum_acf_lag: int
    price_basis: str
    return_type: str
    seed_namespace: str
    empirical_reference_lower_quantile: Decimal
    empirical_reference_upper_quantile: Decimal
    inference_scope: str
    estimator_lock: str
    model_calibration_permitted: bool
    facts: tuple[StylizedFactSpec, ...]

    def __post_init__(self) -> None:
        _non_empty(self.protocol_id, field_name="protocol_id")
        _non_empty(self.protocol_version, field_name="protocol_version")
        _non_empty(self.protocol_status, field_name="protocol_status")
        _non_empty(self.purpose, field_name="purpose")

        fingerprint = _non_empty(
            self.source_flagship_protocol_fingerprint,
            field_name="source_flagship_protocol_fingerprint",
        )
        if _SHA256_PATTERN.fullmatch(fingerprint) is None:
            raise StudyProtocolError(
                "source_flagship_protocol_fingerprint must be a lowercase SHA-256"
            )
        _non_empty(self.source_benchmark_family, field_name="source_benchmark_family")

        if (
            not isinstance(self.validation_homogeneity, Decimal)
            or not self.validation_homogeneity.is_finite()
            or self.validation_homogeneity < _ZERO
            or self.validation_homogeneity > _ONE
        ):
            raise StudyProtocolError("validation_homogeneity must be a finite Decimal in [0, 1]")

        if not isinstance(self.direction_cycle, tuple) or len(self.direction_cycle) < 2:
            raise StudyProtocolError("direction_cycle must contain at least two directions")
        if not all(
            isinstance(direction, NarrativeDirection)
            and direction is not NarrativeDirection.NEUTRAL
            for direction in self.direction_cycle
        ):
            raise StudyProtocolError(
                "direction_cycle must contain only bullish or bearish directions"
            )

        burn_in = _positive_int(
            self.burn_in_periods,
            field_name="burn_in_periods",
        )
        horizon = _positive_int(
            self.analysis_horizon,
            field_name="analysis_horizon",
        )
        _positive_int(self.replicate_count, field_name="replicate_count")
        maximum_lag = _positive_int(
            self.maximum_acf_lag,
            field_name="maximum_acf_lag",
        )
        if maximum_lag >= horizon:
            raise StudyProtocolError("maximum_acf_lag must be smaller than analysis_horizon")
        if burn_in >= self.total_periods:
            raise StudyProtocolError("burn_in_periods must be smaller than total_periods")

        if self.price_basis != "mid":
            raise StudyProtocolError("Phase 11A price_basis must be 'mid'")
        if self.return_type != "log":
            raise StudyProtocolError("Phase 11A return_type must be 'log'")
        _non_empty(self.seed_namespace, field_name="seed_namespace")

        lower = self.empirical_reference_lower_quantile
        upper = self.empirical_reference_upper_quantile
        if (
            not isinstance(lower, Decimal)
            or not lower.is_finite()
            or not isinstance(upper, Decimal)
            or not upper.is_finite()
            or lower <= _ZERO
            or upper >= _ONE
            or lower >= upper
        ):
            raise StudyProtocolError(
                "empirical reference quantiles must satisfy 0 < lower < upper < 1"
            )

        if self.inference_scope != _INFERENCE_SCOPE:
            raise StudyProtocolError("invalid stylized-validation inference_scope")
        if self.estimator_lock != _ESTIMATOR_LOCK:
            raise StudyProtocolError("invalid stylized-validation estimator_lock")
        if self.model_calibration_permitted is not False:
            raise StudyProtocolError("stylized validation must not permit model calibration")

        if not isinstance(self.facts, tuple) or not self.facts:
            raise StudyProtocolError("facts must be a non-empty tuple")
        if not all(isinstance(fact, StylizedFactSpec) for fact in self.facts):
            raise StudyProtocolError("facts must contain only StylizedFactSpec values")

        identifiers = tuple(fact.fact_id for fact in self.facts)
        names = tuple(fact.name for fact in self.facts)
        estimators = tuple(fact.estimator_id for fact in self.facts)
        if len(set(identifiers)) != len(identifiers):
            raise StudyProtocolError("stylized fact IDs must be unique")
        if len(set(names)) != len(names):
            raise StudyProtocolError("stylized fact names must be unique")
        if len(set(estimators)) != len(estimators):
            raise StudyProtocolError("stylized estimator IDs must be unique")
        if not self.primary_fact_ids:
            raise StudyProtocolError("at least one primary stylized fact must be prespecified")

        for fact in self.facts:
            parameters = dict(fact.parameters)
            if "maximum_lag" in parameters and parameters["maximum_lag"] != str(
                self.maximum_acf_lag
            ):
                raise StudyProtocolError("fact maximum_lag must match protocol maximum_acf_lag")

    @property
    def total_periods(self) -> int:
        return self.burn_in_periods + self.analysis_horizon

    @property
    def primary_fact_ids(self) -> tuple[str, ...]:
        return tuple(fact.fact_id for fact in self.facts if fact.role is StylizedFactRole.PRIMARY)

    @property
    def diagnostic_fact_ids(self) -> tuple[str, ...]:
        return tuple(
            fact.fact_id for fact in self.facts if fact.role is StylizedFactRole.DIAGNOSTIC
        )

    @property
    def classification_values(self) -> tuple[str, ...]:
        return tuple(item.value for item in ConcordanceClass)

    def to_mapping(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_status": self.protocol_status,
            "purpose": self.purpose,
            "source_lineage": {
                "flagship_protocol_fingerprint": (self.source_flagship_protocol_fingerprint),
                "benchmark_family": self.source_benchmark_family,
                "validation_homogeneity": _decimal_text(self.validation_homogeneity),
                "direction_cycle": [direction.value for direction in self.direction_cycle],
                "schedule_rule": "repeat-cycle-to-total-periods",
            },
            "simulation_design": {
                "burn_in_periods": self.burn_in_periods,
                "analysis_horizon": self.analysis_horizon,
                "total_periods": self.total_periods,
                "replicate_count": self.replicate_count,
                "maximum_acf_lag": self.maximum_acf_lag,
                "price_basis": self.price_basis,
                "return_type": self.return_type,
                "seed_namespace": self.seed_namespace,
                "post_burn_in_only": True,
            },
            "comparison_design": {
                "empirical_reference_lower_quantile": _decimal_text(
                    self.empirical_reference_lower_quantile
                ),
                "empirical_reference_upper_quantile": _decimal_text(
                    self.empirical_reference_upper_quantile
                ),
                "classification_values": list(self.classification_values),
                "inference_scope": self.inference_scope,
                "model_calibration_permitted": self.model_calibration_permitted,
                "estimator_lock": self.estimator_lock,
            },
            "facts": [fact.to_mapping() for fact in self.facts],
        }

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


def stylized_fact_validation_protocol() -> StylizedValidationProtocol:
    """Return the frozen Phase 11A stylized-fact validation contract."""

    return StylizedValidationProtocol(
        protocol_id="stylized-fact-validation-v1",
        protocol_version="1.0.0",
        protocol_status="prespecified-before-validation-execution",
        purpose="external-validity-diagnostic-not-model-calibration",
        source_flagship_protocol_fingerprint=(_SOURCE_FLAGSHIP_PROTOCOL_FINGERPRINT),
        source_benchmark_family="narrative-stability-v1",
        validation_homogeneity=Decimal("0"),
        direction_cycle=(
            NarrativeDirection.BULLISH,
            NarrativeDirection.BEARISH,
            NarrativeDirection.BULLISH,
            NarrativeDirection.BEARISH,
        ),
        burn_in_periods=256,
        analysis_horizon=4096,
        replicate_count=16,
        maximum_acf_lag=20,
        price_basis="mid",
        return_type="log",
        seed_namespace="stylized-validation-v1",
        empirical_reference_lower_quantile=Decimal("0.05"),
        empirical_reference_upper_quantile=Decimal("0.95"),
        inference_scope=_INFERENCE_SCOPE,
        estimator_lock=_ESTIMATOR_LOCK,
        model_calibration_permitted=False,
        facts=(
            StylizedFactSpec(
                fact_id="SF-01",
                name="return-linear-dependence",
                role=StylizedFactRole.DIAGNOSTIC,
                estimator_id="log-return-acf",
                expected_relation=(StylizedFactExpectation.WEAK_RETURN_AUTOCORRELATION),
                parameters=(
                    ("maximum_lag", "20"),
                    ("series", "log-mid-return"),
                    ("summary", "lag-vector-and-mean-absolute-acf"),
                ),
            ),
            StylizedFactSpec(
                fact_id="SF-02",
                name="return-tail-shape",
                role=StylizedFactRole.DIAGNOSTIC,
                estimator_id="return-tail-shape",
                expected_relation=StylizedFactExpectation.HEAVIER_THAN_GAUSSIAN,
                parameters=(
                    (
                        "gaussian_two_sided_tail_probability",
                        "0.002699796063260207",
                    ),
                    (
                        "kurtosis_definition",
                        "m4-over-m2-squared-minus-3",
                    ),
                    ("series", "log-mid-return"),
                    ("tail_threshold_sigma", "3"),
                ),
            ),
            StylizedFactSpec(
                fact_id="SF-03",
                name="volatility-clustering",
                role=StylizedFactRole.DIAGNOSTIC,
                estimator_id="absolute-log-return-acf",
                expected_relation=(StylizedFactExpectation.POSITIVE_VOLATILITY_PERSISTENCE),
                parameters=(
                    ("maximum_lag", "20"),
                    ("series", "absolute-log-mid-return"),
                    ("summary", "lag-vector-and-mean-acf"),
                ),
            ),
            StylizedFactSpec(
                fact_id="SF-04",
                name="aggressor-flow-price-impact",
                role=StylizedFactRole.PRIMARY,
                estimator_id="aggressor-flow-price-impact-ols",
                expected_relation=(StylizedFactExpectation.POSITIVE_AGGRESSOR_FLOW_PRICE_IMPACT),
                parameters=(
                    (
                        "flow_series",
                        "aggressor-executed-flow-imbalance",
                    ),
                    ("intercept", "true"),
                    (
                        "price_response",
                        "same-interval-log-mid-return",
                    ),
                ),
            ),
            StylizedFactSpec(
                fact_id="SF-05",
                name="liquidity-conditioned-price-impact",
                role=StylizedFactRole.PRIMARY,
                estimator_id="depth-conditioned-aggressor-flow-impact-ols",
                expected_relation=(StylizedFactExpectation.STRONGER_IMPACT_AT_LOW_DEPTH),
                parameters=(
                    (
                        "comparison",
                        "absolute-slope-low-greater-than-high",
                    ),
                    (
                        "depth_series",
                        "pre-interval-thin-side-depth",
                    ),
                    (
                        "flow_series",
                        "aggressor-executed-flow-imbalance",
                    ),
                    ("high_depth_quantile", "0.75"),
                    ("low_depth_quantile", "0.25"),
                    (
                        "price_response",
                        "same-interval-log-mid-return",
                    ),
                ),
            ),
            StylizedFactSpec(
                fact_id="SF-06",
                name="liquidity-fragility",
                role=StylizedFactRole.PRIMARY,
                estimator_id="liquidity-fragility-spearman",
                expected_relation=StylizedFactExpectation.LIQUIDITY_FRAGILITY,
                parameters=(
                    (
                        "depletion_series",
                        "relative-thin-side-depth-drop",
                    ),
                    ("expected_depletion_sign", "positive"),
                    ("expected_pre_depth_sign", "negative"),
                    (
                        "pre_depth_series",
                        "pre-interval-thin-side-depth",
                    ),
                    (
                        "response",
                        "same-interval-absolute-log-mid-return",
                    ),
                ),
            ),
            StylizedFactSpec(
                fact_id="SF-07",
                name="aggressor-sign-persistence",
                role=StylizedFactRole.DIAGNOSTIC,
                estimator_id="aggressor-sign-acf",
                expected_relation=(StylizedFactExpectation.POSITIVE_ORDER_SIGN_PERSISTENCE),
                parameters=(
                    ("maximum_lag", "20"),
                    (
                        "sign_source",
                        "aggressor-executed-flow-imbalance",
                    ),
                    ("summary", "lag-vector-and-mean-acf"),
                    ("zero_flow_intervals", "omit"),
                ),
            ),
        ),
    )


def bundled_stylized_validation_protocol_mapping() -> dict[str, object]:
    """Load the distributed machine-readable Phase 11A protocol snapshot."""

    path = resources.files("abmforge_finance.study").joinpath(
        "specs/stylized_fact_validation_v1.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StudyProtocolError("bundled stylized-validation protocol JSON must be an object")
    return value


def verify_bundled_stylized_validation_protocol(
    protocol: StylizedValidationProtocol,
) -> None:
    """Verify runtime identity against the distributed JSON snapshot."""

    if not isinstance(protocol, StylizedValidationProtocol):
        raise TypeError("protocol must be a StylizedValidationProtocol")
    if protocol.to_mapping() != bundled_stylized_validation_protocol_mapping():
        raise StudyProtocolError("runtime stylized-validation protocol does not match bundled JSON")


def stylized_validation_seed_tuple(
    protocol: StylizedValidationProtocol,
) -> tuple[int, ...]:
    """Derive the fixed independent Phase 11 simulation replicate seeds."""

    if not isinstance(protocol, StylizedValidationProtocol):
        raise TypeError("protocol must be a StylizedValidationProtocol")
    seeds = tuple(
        int.from_bytes(
            hashlib.sha256(
                (f"{protocol.fingerprint}:{protocol.seed_namespace}:{index:08d}").encode()
            ).digest()[:8],
            "big",
        )
        for index in range(protocol.replicate_count)
    )
    if len(set(seeds)) != len(seeds):
        raise StudyProtocolError("stylized-validation seed derivation produced a duplicate")
    return seeds


def build_stylized_validation_benchmark_config(
    protocol: StylizedValidationProtocol,
) -> NarrativeStabilityBenchmarkConfig:
    """Expand the frozen flagship control ecology to the long validation horizon."""

    if not isinstance(protocol, StylizedValidationProtocol):
        raise TypeError("protocol must be a StylizedValidationProtocol")

    flagship = flagship_narrative_stability_protocol()
    if flagship.fingerprint != protocol.source_flagship_protocol_fingerprint:
        raise StudyProtocolError("flagship protocol fingerprint no longer matches Phase 11 lineage")
    if flagship.to_mapping().get("benchmark_family") != (protocol.source_benchmark_family):
        raise StudyProtocolError("flagship benchmark family no longer matches Phase 11 lineage")

    base = flagship.benchmark_config
    if base.direction_schedule != protocol.direction_cycle:
        raise StudyProtocolError("flagship direction cycle no longer matches Phase 11 lineage")

    cycle = protocol.direction_cycle
    repeats, remainder = divmod(protocol.total_periods, len(cycle))
    schedule = cycle * repeats + cycle[:remainder]
    if len(schedule) != protocol.total_periods:
        raise StudyProtocolError("stylized-validation schedule expansion produced wrong horizon")

    return replace(
        base,
        direction_schedule=schedule,
        scenario_id=protocol.protocol_id,
    )
