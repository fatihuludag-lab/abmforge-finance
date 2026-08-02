"""Tests for exact instrument grid validation and conversion."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    Instrument,
    InvalidInstrumentError,
    InvalidPriceError,
    InvalidQuantityError,
)


def make_instrument() -> Instrument:
    """Return a representative instrument definition."""
    return Instrument(
        instrument_id="ACME",
        tick_size=Decimal("0.05"),
        lot_size=Decimal("0.25"),
        quote_currency="USD",
    )


def test_instrument_converts_exact_prices_and_quantities() -> None:
    """Aligned decimal values round-trip through integer ticks and lots."""
    instrument = make_instrument()

    assert instrument.price_to_ticks(Decimal("10.25")) == 205
    assert instrument.ticks_to_price(205) == Decimal("10.25")
    assert instrument.quantity_to_lots(Decimal("3.50")) == 14
    assert instrument.lots_to_quantity(14) == Decimal("3.50")


@pytest.mark.parametrize("field", ["instrument_id", "quote_currency"])
def test_instrument_rejects_empty_identifiers(field: str) -> None:
    """Required string identifiers cannot be blank."""
    values: dict[str, object] = {
        "instrument_id": "ACME",
        "tick_size": Decimal("0.01"),
        "lot_size": Decimal("1"),
        "quote_currency": "USD",
    }
    values[field] = "  "

    with pytest.raises(InvalidInstrumentError):
        Instrument(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tick_size", Decimal("0")),
        ("tick_size", Decimal("-0.01")),
        ("tick_size", Decimal("NaN")),
        ("lot_size", Decimal("0")),
        ("lot_size", Decimal("Infinity")),
        ("lot_size", 1.0),
    ],
)
def test_instrument_rejects_invalid_grid_values(field: str, value: object) -> None:
    """Tick and lot sizes must be finite positive Decimals."""
    values: dict[str, object] = {
        "instrument_id": "ACME",
        "tick_size": Decimal("0.01"),
        "lot_size": Decimal("1"),
        "quote_currency": "USD",
    }
    values[field] = value

    with pytest.raises(InvalidInstrumentError):
        Instrument(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1"), Decimal("10.03")])
def test_instrument_rejects_invalid_prices(price: Decimal) -> None:
    """Prices must be positive and exactly tick aligned."""
    with pytest.raises(InvalidPriceError):
        make_instrument().validate_price(price)


def test_instrument_rejects_non_decimal_price() -> None:
    """Binary floating-point prices are rejected at the public domain boundary."""
    with pytest.raises(InvalidPriceError):
        make_instrument().validate_price(10.25)  # type: ignore[arg-type]


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1"), Decimal("1.10")])
def test_instrument_rejects_invalid_quantities(quantity: Decimal) -> None:
    """Quantities must be positive and exactly lot aligned."""
    with pytest.raises(InvalidQuantityError):
        make_instrument().validate_quantity(quantity)


@pytest.mark.parametrize("ticks", [0, -1, 1.0, True])
def test_ticks_to_price_rejects_non_positive_integers(ticks: object) -> None:
    """Tick conversion accepts only positive non-boolean integers."""
    with pytest.raises(InvalidPriceError):
        make_instrument().ticks_to_price(ticks)  # type: ignore[arg-type]


@pytest.mark.parametrize("lots", [0, -1, 1.0, False])
def test_lots_to_quantity_rejects_non_positive_integers(lots: object) -> None:
    """Lot conversion accepts only positive non-boolean integers."""
    with pytest.raises(InvalidQuantityError):
        make_instrument().lots_to_quantity(lots)  # type: ignore[arg-type]
