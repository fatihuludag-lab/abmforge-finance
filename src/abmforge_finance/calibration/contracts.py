"""Immutable contracts for baseline market calibration experiments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from abmforge_finance.exceptions import InvalidCalibrationError

_MAX_SEED = (1 << 64) - 1


def _non_empty(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidCalibrationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidCalibrationError(f"{field_name} must be a positive integer")
    return value


def _seed(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidCalibrationError("seed must be an integer")
    if value < 0 or value > _MAX_SEED:
        raise InvalidCalibrationError(f"seed must be in [0, {_MAX_SEED}]")
    return value


@dataclass(frozen=True, slots=True)
class CalibrationScenario:
    """Canonical scenario/treatment specification independent of replicate seed."""

    scenario_id: str
    treatment_id: str
    periods: int
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        scenario_id = _non_empty(self.scenario_id, field_name="scenario_id")
        treatment_id = _non_empty(self.treatment_id, field_name="treatment_id")
        periods = _positive_int(self.periods, field_name="periods")
        if not isinstance(self.parameters, tuple):
            raise InvalidCalibrationError("parameters must be a tuple of string pairs")

        normalized: list[tuple[str, str]] = []
        for item in self.parameters:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str)
                or not item[0].strip()
            ):
                raise InvalidCalibrationError(
                    "parameters must contain non-empty string keys and string values"
                )
            normalized.append((item[0].strip(), item[1]))

        keys = tuple(key for key, _ in normalized)
        if len(set(keys)) != len(keys):
            raise InvalidCalibrationError("parameter keys must be unique")

        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "treatment_id", treatment_id)
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "parameters", tuple(sorted(normalized)))

    @property
    def fingerprint(self) -> str:
        """Return a canonical SHA-256 fingerprint excluding replicate seed."""

        payload = {
            "parameters": [list(item) for item in self.parameters],
            "periods": self.periods,
            "scenario_id": self.scenario_id,
            "treatment_id": self.treatment_id,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CalibrationRunSpec:
    """One replicate within one scenario/treatment."""

    scenario: CalibrationScenario
    replicate: int
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, CalibrationScenario):
            raise InvalidCalibrationError("scenario must be a CalibrationScenario")
        if (
            isinstance(self.replicate, bool)
            or not isinstance(self.replicate, int)
            or self.replicate < 0
        ):
            raise InvalidCalibrationError("replicate must be a non-negative integer")
        _seed(self.seed)


def validate_seed_tuple(seeds: object) -> tuple[int, ...]:
    """Validate an explicit, ordered, duplicate-free replicate seed tuple."""

    if not isinstance(seeds, tuple) or not seeds:
        raise InvalidCalibrationError("seeds must be a non-empty tuple")
    validated = tuple(_seed(seed) for seed in seeds)
    if len(set(validated)) != len(validated):
        raise InvalidCalibrationError("replicate seeds must be unique")
    return validated
