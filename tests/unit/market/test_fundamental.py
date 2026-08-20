"""Unit tests for deterministic fundamental-value processes."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    ConstantFundamentalValue,
    DeterministicFundamentalPath,
    FundamentalPathExhaustedError,
    FundamentalValueProcess,
    InvalidFundamentalValueError,
    InvalidMarketTimeError,
    SeededFundamentalRandomWalk,
)


def test_constant_process_returns_exact_value_at_any_valid_step() -> None:
    process: FundamentalValueProcess = ConstantFundamentalValue(Decimal("100.25"))
    assert process.value_at(0) == Decimal("100.25")
    assert process.value_at(10_000) == Decimal("100.25")


@pytest.mark.parametrize(
    "value",
    [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 100, "100"],
)
def test_constant_process_rejects_invalid_values(value: object) -> None:
    with pytest.raises(InvalidFundamentalValueError):
        ConstantFundamentalValue(value)  # type: ignore[arg-type]


def test_frozen_path_uses_explicit_start_and_end_steps() -> None:
    process = DeterministicFundamentalPath(
        (Decimal("100"), Decimal("101.5"), Decimal("99.75")),
        start_step=4,
    )
    assert process.start_step == 4
    assert process.end_step == 6
    assert process.value_at(4) == Decimal("100")
    assert process.value_at(5) == Decimal("101.5")
    assert process.value_at(6) == Decimal("99.75")


@pytest.mark.parametrize("step", [0, 3, 7])
def test_frozen_path_fails_explicitly_outside_horizon(step: int) -> None:
    process = DeterministicFundamentalPath((Decimal("100"), Decimal("101")), start_step=4)
    with pytest.raises(FundamentalPathExhaustedError):
        process.value_at(step)


def test_frozen_path_rejects_empty_or_invalid_values() -> None:
    with pytest.raises(InvalidFundamentalValueError):
        DeterministicFundamentalPath(())
    with pytest.raises(InvalidFundamentalValueError):
        DeterministicFundamentalPath((Decimal("100"), Decimal("0")))
    with pytest.raises(InvalidFundamentalValueError):
        DeterministicFundamentalPath([Decimal("100")])  # type: ignore[arg-type]


def test_seeded_walk_has_frozen_algorithmic_path() -> None:
    process = SeededFundamentalRandomWalk(
        Decimal("100"),
        seed=123,
        step_size=Decimal("0.25"),
        max_abs_shock_units=3,
        drift_units=1,
        minimum_value=Decimal("1"),
    )
    assert [process.value_at(step) for step in range(6)] == [
        Decimal("100"),
        Decimal("100.25"),
        Decimal("101.00"),
        Decimal("102.00"),
        Decimal("101.75"),
        Decimal("102.75"),
    ]


def test_seeded_walk_is_call_order_independent() -> None:
    first = SeededFundamentalRandomWalk(
        Decimal("10"), seed=42, step_size=Decimal("0.1"), max_abs_shock_units=2
    )
    second = SeededFundamentalRandomWalk(
        Decimal("10"), seed=42, step_size=Decimal("0.1"), max_abs_shock_units=2
    )
    late = first.value_at(20)
    assert first.value_at(3) == second.value_at(3)
    assert late == second.value_at(20)


def test_seeded_walk_floor_preserves_positive_value() -> None:
    process = SeededFundamentalRandomWalk(
        Decimal("1"),
        seed=0,
        step_size=Decimal("1"),
        max_abs_shock_units=0,
        drift_units=-2,
        minimum_value=Decimal("0.5"),
    )
    assert process.value_at(1) == Decimal("0.5")
    assert process.value_at(10) == Decimal("0.5")


def test_seeded_walk_zero_shock_and_zero_drift_is_constant() -> None:
    process = SeededFundamentalRandomWalk(
        Decimal("25"), seed=999, step_size=Decimal("0.01"), max_abs_shock_units=0
    )
    assert [process.value_at(step) for step in range(10)] == [Decimal("25")] * 10


@pytest.mark.parametrize("step", [-1, True, 1.5, "1"])
def test_processes_reject_invalid_market_steps(step: object) -> None:
    process = ConstantFundamentalValue(Decimal("100"))
    with pytest.raises(InvalidMarketTimeError):
        process.value_at(step)  # type: ignore[arg-type]


def test_seeded_walk_rejects_invalid_configuration() -> None:
    with pytest.raises(InvalidFundamentalValueError):
        SeededFundamentalRandomWalk(
            Decimal("100"), seed=-1, step_size=Decimal("1"), max_abs_shock_units=1
        )
    with pytest.raises(InvalidFundamentalValueError):
        SeededFundamentalRandomWalk(
            Decimal("100"), seed=1, step_size=Decimal("0"), max_abs_shock_units=1
        )
    with pytest.raises(InvalidFundamentalValueError):
        SeededFundamentalRandomWalk(
            Decimal("100"), seed=1, step_size=Decimal("1"), max_abs_shock_units=-1
        )
    with pytest.raises(InvalidFundamentalValueError):
        SeededFundamentalRandomWalk(
            Decimal("0.5"),
            seed=1,
            step_size=Decimal("1"),
            max_abs_shock_units=1,
            minimum_value=Decimal("1"),
        )
