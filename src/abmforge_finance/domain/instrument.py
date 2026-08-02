"""Tradable instrument definitions and exact tick/lot conversions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain._validation import require_decimal, require_non_empty_text
from abmforge_finance.exceptions import (
    InvalidInstrumentError,
    InvalidPriceError,
    InvalidQuantityError,
)

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class Instrument:
    """Define the discrete price and quantity grid of one tradable asset.

    Parameters
    ----------
    instrument_id
        Stable identifier used in orders, trades, and recorded artifacts.
    tick_size
        Smallest permitted positive price increment, represented as ``Decimal``.
    lot_size
        Smallest permitted positive quantity increment, represented as ``Decimal``.
    quote_currency
        Non-empty identifier for the cash denomination, such as ``USD`` or ``TRY``.

    Raises
    ------
    InvalidInstrumentError
        If an identifier is empty or a grid size is non-finite or non-positive.

    Determinism
    -----------
    Tick and lot conversions use exact decimal arithmetic and therefore do not depend
    on binary floating-point rounding.

    Examples
    --------
    >>> from decimal import Decimal
    >>> instrument = Instrument("ACME", Decimal("0.01"), Decimal("1"))
    >>> instrument.price_to_ticks(Decimal("10.25"))
    1025
    """

    instrument_id: str
    tick_size: Decimal
    lot_size: Decimal
    quote_currency: str = "USD"

    def __post_init__(self) -> None:
        require_non_empty_text(
            self.instrument_id,
            field_name="instrument_id",
            error_type=InvalidInstrumentError,
        )
        require_non_empty_text(
            self.quote_currency,
            field_name="quote_currency",
            error_type=InvalidInstrumentError,
        )
        require_decimal(
            self.tick_size,
            field_name="tick_size",
            error_type=InvalidInstrumentError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )
        require_decimal(
            self.lot_size,
            field_name="lot_size",
            error_type=InvalidInstrumentError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )

    def validate_price(self, price: Decimal) -> None:
        """Validate that a price is positive and aligned to the tick grid.

        Parameters
        ----------
        price
            Candidate price as ``Decimal``.

        Raises
        ------
        InvalidPriceError
            If the value is not a finite positive ``Decimal`` or is off tick.

        Determinism
        -----------
        Validation uses exact ``Decimal`` division with remainder.
        """
        validated = require_decimal(
            price,
            field_name="price",
            error_type=InvalidPriceError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )
        _, remainder = divmod(validated, self.tick_size)
        if remainder != _ZERO:
            raise InvalidPriceError(
                f"price {validated} is not aligned to tick_size {self.tick_size}"
            )

    def validate_quantity(self, quantity: Decimal) -> None:
        """Validate that a quantity is positive and aligned to the lot grid.

        Parameters
        ----------
        quantity
            Candidate quantity as ``Decimal``.

        Raises
        ------
        InvalidQuantityError
            If the value is not a finite positive ``Decimal`` or is off lot.

        Determinism
        -----------
        Validation uses exact ``Decimal`` division with remainder.
        """
        validated = require_decimal(
            quantity,
            field_name="quantity",
            error_type=InvalidQuantityError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )
        _, remainder = divmod(validated, self.lot_size)
        if remainder != _ZERO:
            raise InvalidQuantityError(
                f"quantity {validated} is not aligned to lot_size {self.lot_size}"
            )

    def price_to_ticks(self, price: Decimal) -> int:
        """Convert an aligned positive price to its exact integer tick count.

        Parameters
        ----------
        price
            Positive tick-aligned price.

        Returns
        -------
        int
            Number of ticks above zero.

        Raises
        ------
        InvalidPriceError
            If ``price`` violates the instrument price grid.
        """
        self.validate_price(price)
        ticks, _ = divmod(price, self.tick_size)
        return int(ticks)

    def ticks_to_price(self, ticks: int) -> Decimal:
        """Convert a positive integer tick count to an exact price.

        Parameters
        ----------
        ticks
            Positive integer number of ticks.

        Returns
        -------
        Decimal
            Exact price on the instrument grid.

        Raises
        ------
        InvalidPriceError
            If ``ticks`` is not a positive integer.
        """
        if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks <= 0:
            raise InvalidPriceError("ticks must be a positive integer")
        return self.tick_size * ticks

    def quantity_to_lots(self, quantity: Decimal) -> int:
        """Convert an aligned positive quantity to its exact integer lot count.

        Parameters
        ----------
        quantity
            Positive lot-aligned quantity.

        Returns
        -------
        int
            Number of lots.

        Raises
        ------
        InvalidQuantityError
            If ``quantity`` violates the instrument quantity grid.
        """
        self.validate_quantity(quantity)
        lots, _ = divmod(quantity, self.lot_size)
        return int(lots)

    def lots_to_quantity(self, lots: int) -> Decimal:
        """Convert a positive integer lot count to an exact quantity.

        Parameters
        ----------
        lots
            Positive integer number of lots.

        Returns
        -------
        Decimal
            Exact quantity on the instrument grid.

        Raises
        ------
        InvalidQuantityError
            If ``lots`` is not a positive integer.
        """
        if isinstance(lots, bool) or not isinstance(lots, int) or lots <= 0:
            raise InvalidQuantityError("lots must be a positive integer")
        return self.lot_size * lots
