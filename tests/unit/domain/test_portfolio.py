"""Unit tests for immutable deterministic portfolios."""

from decimal import Decimal

import pytest

from abmforge_finance import InvalidPortfolioError, Portfolio


def test_portfolio_normalizes_sorting_and_zero_positions() -> None:
    portfolio = Portfolio(
        "agent-1",
        (("B", Decimal("2")), ("ZERO", Decimal("0")), ("A", Decimal("-1"))),
    )
    assert portfolio.positions == (("A", Decimal("-1")), ("B", Decimal("2")))


def test_quantity_returns_zero_for_absent_instrument() -> None:
    portfolio = Portfolio("agent-1", (("ACME", Decimal("3")),))
    assert portfolio.quantity("ACME") == Decimal("3")
    assert portfolio.quantity("OTHER") == Decimal("0")


def test_with_quantity_delta_is_pure_and_removes_zero() -> None:
    original = Portfolio("agent-1", (("ACME", Decimal("3")),))
    increased = original.with_quantity_delta("ACME", Decimal("2"))
    cleared = increased.with_quantity_delta("ACME", Decimal("-5"))
    assert original.quantity("ACME") == Decimal("3")
    assert increased.quantity("ACME") == Decimal("5")
    assert cleared.positions == ()


@pytest.mark.parametrize("participant_id", ["", "  ", None])
def test_portfolio_requires_non_empty_participant_id(participant_id: object) -> None:
    with pytest.raises(InvalidPortfolioError):
        Portfolio(participant_id)  # type: ignore[arg-type]


def test_portfolio_requires_tuple_positions() -> None:
    with pytest.raises(InvalidPortfolioError):
        Portfolio("agent-1", [("ACME", Decimal("1"))])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "positions",
    [
        (("ACME", Decimal("1")), ("ACME", Decimal("2"))),
        (("", Decimal("1")),),
        (("ACME", Decimal("NaN")),),
        (("ACME", 1),),
        (("ACME",),),
    ],
)
def test_portfolio_rejects_invalid_positions(
    positions: tuple[tuple[object, ...], ...],
) -> None:
    with pytest.raises(InvalidPortfolioError):
        Portfolio("agent-1", positions)  # type: ignore[arg-type]


def test_quantity_and_delta_validate_inputs() -> None:
    portfolio = Portfolio("agent-1")
    with pytest.raises(InvalidPortfolioError):
        portfolio.quantity(1)  # type: ignore[arg-type]
    with pytest.raises(InvalidPortfolioError):
        portfolio.with_quantity_delta("ACME", 1)  # type: ignore[arg-type]
