"""Typed raw Binance USD-M market-data messages for Phase 11."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from abmforge_finance.exceptions import (
    InvalidMetricInputError,
    StudyProtocolError,
)
from abmforge_finance.study.binance_usdm_contract import (
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)


def _required(
    payload: Mapping[str, object],
    key: str,
) -> object:
    try:
        return payload[key]
    except KeyError as exc:
        raise InvalidMetricInputError(f"Binance payload is missing required field {key!r}") from exc


def _text(
    value: object,
    *,
    label: str,
) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidMetricInputError(f"{label} must be a non-empty string")
    return value


def _integer(
    value: object,
    *,
    label: str,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidMetricInputError(f"{label} must be a non-negative integer")

    if value < 0:
        raise InvalidMetricInputError(f"{label} must be a non-negative integer")

    return value


def _boolean(
    value: object,
    *,
    label: str,
) -> bool:
    if not isinstance(value, bool):
        raise InvalidMetricInputError(f"{label} must be a boolean")
    return value


def _decimal_string(
    value: object,
    *,
    label: str,
) -> Decimal:
    if not isinstance(value, str):
        raise InvalidMetricInputError(f"{label} must be a decimal string")

    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidMetricInputError(f"{label} must be a valid decimal string") from exc

    if not number.is_finite():
        raise InvalidMetricInputError(f"{label} must be finite")

    return number


def _sequence(
    value: object,
    *,
    label: str,
) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidMetricInputError(f"{label} must be an array")
    return value


@dataclass(frozen=True, slots=True)
class BinanceUsdMBookLevel:
    """One absolute Binance USD-M price-level quantity."""

    price: Decimal
    quantity: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.price, Decimal):
            raise TypeError("price must be a Decimal")

        if not isinstance(self.quantity, Decimal):
            raise TypeError("quantity must be a Decimal")

        if not self.price.is_finite() or self.price <= 0:
            raise InvalidMetricInputError("book-level price must be positive and finite")

        if not self.quantity.is_finite() or self.quantity < 0:
            raise InvalidMetricInputError("book-level quantity must be non-negative and finite")


def _book_levels(
    value: object,
    *,
    label: str,
    zero_quantity_allowed: bool,
) -> tuple[BinanceUsdMBookLevel, ...]:
    rows = _sequence(value, label=label)
    output: list[BinanceUsdMBookLevel] = []

    for index, row in enumerate(rows):
        values = _sequence(
            row,
            label=f"{label}[{index}]",
        )

        if len(values) != 2:
            raise InvalidMetricInputError(f"{label}[{index}] must contain price and quantity")

        level = BinanceUsdMBookLevel(
            price=_decimal_string(
                values[0],
                label=f"{label}[{index}][0]",
            ),
            quantity=_decimal_string(
                values[1],
                label=f"{label}[{index}][1]",
            ),
        )

        if not zero_quantity_allowed and level.quantity == 0:
            raise InvalidMetricInputError(f"{label}[{index}] snapshot quantity must be positive")

        output.append(level)

    return tuple(output)


def _validate_contract_symbol(
    *,
    symbol: str,
    symbol_type: int,
    contract: BinanceUsdMEmpiricalContract,
) -> None:
    if symbol != contract.symbol:
        raise StudyProtocolError("Binance event symbol does not match the frozen contract")

    if symbol_type != contract.required_symbol_type:
        raise StudyProtocolError("Binance event symbol type does not match USD-M contract")


@dataclass(frozen=True, slots=True)
class BinanceUsdMAggTradeEvent:
    """One validated raw Binance USD-M aggregate-trade event."""

    event_time_ms: int
    trade_time_ms: int
    symbol: str
    symbol_type: int
    aggregate_trade_id: int
    price: Decimal
    quantity: Decimal
    normal_quantity: Decimal
    first_trade_id: int
    last_trade_id: int
    buyer_is_maker: bool

    def __post_init__(self) -> None:
        for label, value in (
            ("event_time_ms", self.event_time_ms),
            ("trade_time_ms", self.trade_time_ms),
            ("aggregate_trade_id", self.aggregate_trade_id),
            ("first_trade_id", self.first_trade_id),
            ("last_trade_id", self.last_trade_id),
        ):
            _integer(value, label=label)

        _text(self.symbol, label="symbol")

        if self.symbol != self.symbol.upper():
            raise InvalidMetricInputError("symbol must be uppercase")

        if self.symbol_type != 1:
            raise InvalidMetricInputError("symbol_type must identify USD-M as 1")

        if not isinstance(self.price, Decimal):
            raise TypeError("price must be a Decimal")

        if not isinstance(self.quantity, Decimal):
            raise TypeError("quantity must be a Decimal")

        if not isinstance(self.normal_quantity, Decimal):
            raise TypeError("normal_quantity must be a Decimal")

        if not self.price.is_finite() or self.price <= 0:
            raise InvalidMetricInputError("aggregate-trade price must be positive and finite")

        if not self.quantity.is_finite() or self.quantity <= 0:
            raise InvalidMetricInputError("aggregate-trade quantity must be positive and finite")

        if not self.normal_quantity.is_finite() or self.normal_quantity < 0:
            raise InvalidMetricInputError("normal quantity must be non-negative and finite")

        if self.normal_quantity > self.quantity:
            raise InvalidMetricInputError("normal quantity cannot exceed total quantity")

        if self.first_trade_id > self.last_trade_id:
            raise InvalidMetricInputError("first_trade_id must not exceed last_trade_id")

        _boolean(
            self.buyer_is_maker,
            label="buyer_is_maker",
        )

    @property
    def aggressor_sign(self) -> int:
        """Return +1 for buy aggressor and -1 for sell aggressor."""

        return -1 if self.buyer_is_maker else 1

    @property
    def signed_normal_quantity(self) -> Decimal:
        """Return RPI-excluded quantity with aggressor direction."""

        return self.normal_quantity if self.aggressor_sign > 0 else -self.normal_quantity

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
        *,
        contract: BinanceUsdMEmpiricalContract | None = None,
    ) -> BinanceUsdMAggTradeEvent:
        """Parse and validate one raw aggregate-trade payload."""

        active_contract = binance_usdm_empirical_contract() if contract is None else contract

        event_type = _text(
            _required(payload, "e"),
            label="e",
        )

        if event_type != "aggTrade":
            raise InvalidMetricInputError("aggregate-trade event type must be aggTrade")

        symbol = _text(
            _required(payload, "s"),
            label="s",
        )

        symbol_type = _integer(
            _required(payload, "st"),
            label="st",
        )

        _validate_contract_symbol(
            symbol=symbol,
            symbol_type=symbol_type,
            contract=active_contract,
        )

        return cls(
            event_time_ms=_integer(
                _required(payload, "E"),
                label="E",
            ),
            trade_time_ms=_integer(
                _required(payload, "T"),
                label="T",
            ),
            symbol=symbol,
            symbol_type=symbol_type,
            aggregate_trade_id=_integer(
                _required(payload, "a"),
                label="a",
            ),
            price=_decimal_string(
                _required(payload, "p"),
                label="p",
            ),
            quantity=_decimal_string(
                _required(payload, "q"),
                label="q",
            ),
            normal_quantity=_decimal_string(
                _required(payload, "nq"),
                label="nq",
            ),
            first_trade_id=_integer(
                _required(payload, "f"),
                label="f",
            ),
            last_trade_id=_integer(
                _required(payload, "l"),
                label="l",
            ),
            buyer_is_maker=_boolean(
                _required(payload, "m"),
                label="m",
            ),
        )


@dataclass(frozen=True, slots=True)
class BinanceUsdMDepthUpdateEvent:
    """One validated Binance USD-M diff-depth event."""

    event_time_ms: int
    transaction_time_ms: int
    symbol: str
    pair: str
    symbol_type: int
    first_update_id: int
    final_update_id: int
    previous_final_update_id: int
    bid_updates: tuple[BinanceUsdMBookLevel, ...]
    ask_updates: tuple[BinanceUsdMBookLevel, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("event_time_ms", self.event_time_ms),
            ("transaction_time_ms", self.transaction_time_ms),
            ("first_update_id", self.first_update_id),
            ("final_update_id", self.final_update_id),
            (
                "previous_final_update_id",
                self.previous_final_update_id,
            ),
        ):
            _integer(value, label=label)

        if self.first_update_id > self.final_update_id:
            raise InvalidMetricInputError("first_update_id must not exceed final_update_id")

        if self.symbol_type != 1:
            raise InvalidMetricInputError("symbol_type must identify USD-M as 1")

        _text(self.symbol, label="symbol")
        _text(self.pair, label="pair")

        if self.symbol != self.symbol.upper() or self.pair != self.pair.upper():
            raise InvalidMetricInputError("symbol and pair must be uppercase")

        if not isinstance(self.bid_updates, tuple):
            raise TypeError("bid_updates must be a tuple")

        if not isinstance(self.ask_updates, tuple):
            raise TypeError("ask_updates must be a tuple")

        if not all(isinstance(level, BinanceUsdMBookLevel) for level in self.bid_updates):
            raise TypeError("bid_updates must contain BinanceUsdMBookLevel")

        if not all(isinstance(level, BinanceUsdMBookLevel) for level in self.ask_updates):
            raise TypeError("ask_updates must contain BinanceUsdMBookLevel")

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
        *,
        contract: BinanceUsdMEmpiricalContract | None = None,
    ) -> BinanceUsdMDepthUpdateEvent:
        """Parse and validate one raw diff-depth payload."""

        active_contract = binance_usdm_empirical_contract() if contract is None else contract

        event_type = _text(
            _required(payload, "e"),
            label="e",
        )

        if event_type != "depthUpdate":
            raise InvalidMetricInputError("depth event type must be depthUpdate")

        symbol = _text(
            _required(payload, "s"),
            label="s",
        )

        pair = _text(
            _required(payload, "ps"),
            label="ps",
        )

        symbol_type = _integer(
            _required(payload, "st"),
            label="st",
        )

        _validate_contract_symbol(
            symbol=symbol,
            symbol_type=symbol_type,
            contract=active_contract,
        )

        if pair != active_contract.pair:
            raise StudyProtocolError("Binance depth pair does not match the frozen contract")

        return cls(
            event_time_ms=_integer(
                _required(payload, "E"),
                label="E",
            ),
            transaction_time_ms=_integer(
                _required(payload, "T"),
                label="T",
            ),
            symbol=symbol,
            pair=pair,
            symbol_type=symbol_type,
            first_update_id=_integer(
                _required(payload, "U"),
                label="U",
            ),
            final_update_id=_integer(
                _required(payload, "u"),
                label="u",
            ),
            previous_final_update_id=_integer(
                _required(payload, "pu"),
                label="pu",
            ),
            bid_updates=_book_levels(
                _required(payload, "b"),
                label="b",
                zero_quantity_allowed=True,
            ),
            ask_updates=_book_levels(
                _required(payload, "a"),
                label="a",
                zero_quantity_allowed=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class BinanceUsdMDepthSnapshot:
    """One validated REST depth snapshot."""

    symbol: str
    last_update_id: int
    event_time_ms: int
    transaction_time_ms: int
    bids: tuple[BinanceUsdMBookLevel, ...]
    asks: tuple[BinanceUsdMBookLevel, ...]

    def __post_init__(self) -> None:
        _text(self.symbol, label="symbol")

        if self.symbol != self.symbol.upper():
            raise InvalidMetricInputError("snapshot symbol must be uppercase")

        for label, value in (
            ("last_update_id", self.last_update_id),
            ("event_time_ms", self.event_time_ms),
            ("transaction_time_ms", self.transaction_time_ms),
        ):
            _integer(value, label=label)

        if not self.bids:
            raise InvalidMetricInputError("snapshot bids must not be empty")

        if not self.asks:
            raise InvalidMetricInputError("snapshot asks must not be empty")

        if not all(isinstance(level, BinanceUsdMBookLevel) for level in self.bids):
            raise TypeError("bids must contain BinanceUsdMBookLevel")

        if not all(isinstance(level, BinanceUsdMBookLevel) for level in self.asks):
            raise TypeError("asks must contain BinanceUsdMBookLevel")

        if max(level.price for level in self.bids) >= min(level.price for level in self.asks):
            raise InvalidMetricInputError("snapshot must contain a positive bid-ask spread")

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
        *,
        symbol: str = "BTCUSDT",
        contract: BinanceUsdMEmpiricalContract | None = None,
    ) -> BinanceUsdMDepthSnapshot:
        """Parse one `/fapi/v1/depth` response."""

        active_contract = binance_usdm_empirical_contract() if contract is None else contract

        if symbol != active_contract.symbol:
            raise StudyProtocolError("snapshot symbol does not match the frozen contract")

        return cls(
            symbol=symbol,
            last_update_id=_integer(
                _required(payload, "lastUpdateId"),
                label="lastUpdateId",
            ),
            event_time_ms=_integer(
                _required(payload, "E"),
                label="E",
            ),
            transaction_time_ms=_integer(
                _required(payload, "T"),
                label="T",
            ),
            bids=_book_levels(
                _required(payload, "bids"),
                label="bids",
                zero_quantity_allowed=False,
            ),
            asks=_book_levels(
                _required(payload, "asks"),
                label="asks",
                zero_quantity_allowed=False,
            ),
        )
