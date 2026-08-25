"""Network preflight and REST access for Binance USD-M empirical capture."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.binance_usdm_contract import (
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMDepthSnapshot,
)


class BinanceUsdMNetworkError(InvalidMetricInputError):
    """Raised when the empirical source cannot satisfy the frozen contract."""


@dataclass(frozen=True, slots=True)
class BinanceUsdMExchangePreflight:
    """Validated Binance exchangeInfo identity for the frozen symbol."""

    symbol: str
    pair: str
    contract_type: str
    status: str
    quote_asset: str
    margin_asset: str
    server_timezone: str

    def __post_init__(self) -> None:
        for label, value in (
            ("symbol", self.symbol),
            ("pair", self.pair),
            ("contract_type", self.contract_type),
            ("status", self.status),
            ("quote_asset", self.quote_asset),
            ("margin_asset", self.margin_asset),
            ("server_timezone", self.server_timezone),
        ):
            if not isinstance(value, str) or not value:
                raise BinanceUsdMNetworkError(f"{label} must be a non-empty string")


def _json_object(raw_json: str, *, label: str) -> Mapping[str, object]:
    if not isinstance(raw_json, str) or not raw_json:
        raise BinanceUsdMNetworkError(f"{label} must be non-empty JSON text")

    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise BinanceUsdMNetworkError(f"{label} is invalid JSON") from exc

    if not isinstance(value, dict):
        raise BinanceUsdMNetworkError(f"{label} must contain a JSON object")

    return value


def _required_text(
    payload: Mapping[str, object],
    key: str,
) -> str:
    value = payload.get(key)

    if not isinstance(value, str) or not value:
        raise BinanceUsdMNetworkError(f"exchangeInfo field {key!r} must be a non-empty string")

    return value


def parse_binance_usdm_exchange_info(
    raw_json: str,
    *,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> BinanceUsdMExchangePreflight:
    """Validate exchangeInfo against the frozen empirical contract."""

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    payload = _json_object(
        raw_json,
        label="exchangeInfo",
    )

    timezone = payload.get("timezone")

    if not isinstance(timezone, str) or not timezone:
        raise BinanceUsdMNetworkError("exchangeInfo timezone must be a non-empty string")

    symbols = payload.get("symbols")

    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
        raise BinanceUsdMNetworkError("exchangeInfo symbols must be an array")

    matches: list[Mapping[str, object]] = []

    for item in symbols:
        if not isinstance(item, dict):
            raise BinanceUsdMNetworkError("exchangeInfo symbol entries must be objects")

        if item.get("symbol") == active_contract.symbol:
            matches.append(item)

    if len(matches) != 1:
        raise BinanceUsdMNetworkError("exchangeInfo must contain exactly one frozen symbol")

    symbol = matches[0]

    preflight = BinanceUsdMExchangePreflight(
        symbol=_required_text(symbol, "symbol"),
        pair=_required_text(symbol, "pair"),
        contract_type=_required_text(
            symbol,
            "contractType",
        ),
        status=_required_text(symbol, "status"),
        quote_asset=_required_text(
            symbol,
            "quoteAsset",
        ),
        margin_asset=_required_text(
            symbol,
            "marginAsset",
        ),
        server_timezone=timezone,
    )

    if preflight.symbol != active_contract.symbol:
        raise BinanceUsdMNetworkError("exchangeInfo symbol does not match frozen contract")

    if preflight.pair != active_contract.pair:
        raise BinanceUsdMNetworkError("exchangeInfo pair does not match frozen contract")

    if preflight.contract_type != active_contract.contract_type:
        raise BinanceUsdMNetworkError("exchangeInfo contract type does not match frozen contract")

    if preflight.status != active_contract.trading_status:
        raise BinanceUsdMNetworkError("exchangeInfo symbol is not in frozen trading status")

    if preflight.quote_asset != active_contract.quote_asset:
        raise BinanceUsdMNetworkError("exchangeInfo quote asset does not match frozen contract")

    if preflight.margin_asset != active_contract.margin_asset:
        raise BinanceUsdMNetworkError("exchangeInfo margin asset does not match frozen contract")

    if preflight.server_timezone != active_contract.timezone:
        raise BinanceUsdMNetworkError("exchangeInfo timezone does not match frozen contract")

    return preflight


def _http_get_text(
    url: str,
    *,
    timeout_seconds: float,
) -> str:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "abmforge-finance/empirical",
        },
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            payload = cast(bytes, response.read())
    except (HTTPError, URLError, TimeoutError) as exc:
        raise BinanceUsdMNetworkError(f"Binance HTTP request failed: {url}") from exc

    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BinanceUsdMNetworkError("Binance HTTP response is not UTF-8") from exc


def fetch_binance_usdm_exchange_info(
    *,
    timeout_seconds: float = 10.0,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> tuple[str, BinanceUsdMExchangePreflight]:
    """Fetch and validate the live Binance exchangeInfo document."""

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    raw = _http_get_text(
        (active_contract.rest_base_url + active_contract.exchange_info_path),
        timeout_seconds=timeout_seconds,
    )

    return (
        raw,
        parse_binance_usdm_exchange_info(
            raw,
            contract=active_contract,
        ),
    )


def fetch_binance_usdm_depth_snapshot(
    *,
    timeout_seconds: float = 10.0,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> tuple[str, BinanceUsdMDepthSnapshot]:
    """Fetch and parse the frozen 1000-level Binance depth snapshot."""

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    url = (
        active_contract.rest_base_url
        + active_contract.depth_snapshot_path
        + "?symbol="
        + active_contract.symbol
        + "&limit="
        + str(active_contract.depth_snapshot_limit)
    )

    raw = _http_get_text(
        url,
        timeout_seconds=timeout_seconds,
    )

    payload = _json_object(
        raw,
        label="depth snapshot",
    )

    return (
        raw,
        BinanceUsdMDepthSnapshot.from_mapping(
            payload,
            symbol=active_contract.symbol,
            contract=active_contract,
        ),
    )


def load_websocket_connect() -> Callable[..., Any]:
    """Load the optional WebSocket dependency only when live capture is used."""

    try:
        module = import_module("websockets.asyncio.client")
    except ImportError as exc:
        raise BinanceUsdMNetworkError(
            "live Binance capture requires the optional "
            "'empirical' dependency: "
            "pip install 'abmforge-finance[empirical]'"
        ) from exc

    connect = getattr(
        module,
        "connect",
        None,
    )

    if not callable(connect):
        raise BinanceUsdMNetworkError(
            "installed websockets package does not expose websockets.asyncio.client.connect"
        )

    return cast(Callable[..., Any], connect)
