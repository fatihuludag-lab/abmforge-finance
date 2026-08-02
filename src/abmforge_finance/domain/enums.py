"""Enumerations used by finance-domain value objects."""

from __future__ import annotations

from enum import Enum


class Side(str, Enum):
    """Order direction in the central limit order book."""

    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> Side:
        """Return the opposite trading side.

        Returns
        -------
        Side
            ``SELL`` for ``BUY`` and ``BUY`` for ``SELL``.

        Determinism
        -----------
        The result is a pure function of the enum member.
        """
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(str, Enum):
    """Supported order instructions for the first research core."""

    LIMIT = "limit"
    MARKET = "market"


class TimeInForce(str, Enum):
    """Supported lifetime instructions for submitted orders."""

    GOOD_TIL_CANCELLED = "gtc"
    IMMEDIATE_OR_CANCEL = "ioc"
