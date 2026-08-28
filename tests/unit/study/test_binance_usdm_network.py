"""Tests for Binance USD-M network preflight and REST parsing."""

from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from abmforge_finance.study.binance_usdm_network import (
    BinanceUsdMNetworkError,
    parse_binance_usdm_exchange_info,
)


def _exchange_info() -> str:
    return json.dumps(
        {
            "timezone": "UTC",
            "serverTime": 123456789,
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "pair": "BTCUSDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "marginAsset": "USDT",
                },
                {
                    "symbol": "ETHUSDT",
                    "pair": "ETHUSDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDT",
                    "marginAsset": "USDT",
                },
            ],
        },
        separators=(",", ":"),
    )


def test_exchange_info_preflight_matches_frozen_contract() -> None:
    result = parse_binance_usdm_exchange_info(_exchange_info())

    assert result.symbol == "BTCUSDT"
    assert result.pair == "BTCUSDT"
    assert result.contract_type == "PERPETUAL"
    assert result.status == "TRADING"
    assert result.quote_asset == "USDT"
    assert result.margin_asset == "USDT"
    assert result.server_timezone == "UTC"


def test_exchange_info_rejects_non_trading_symbol() -> None:
    value = json.loads(_exchange_info())

    value["symbols"][0]["status"] = "BREAK"

    with pytest.raises(
        BinanceUsdMNetworkError,
        match="trading status",
    ):
        parse_binance_usdm_exchange_info(json.dumps(value))


def test_exchange_info_rejects_wrong_contract_type() -> None:
    value = json.loads(_exchange_info())

    value["symbols"][0]["contractType"] = "CURRENT_QUARTER"

    with pytest.raises(
        BinanceUsdMNetworkError,
        match="contract type",
    ):
        parse_binance_usdm_exchange_info(json.dumps(value))


def test_exchange_info_rejects_wrong_margin_asset() -> None:
    value = json.loads(_exchange_info())

    value["symbols"][0]["marginAsset"] = "BTC"

    with pytest.raises(
        BinanceUsdMNetworkError,
        match="margin asset",
    ):
        parse_binance_usdm_exchange_info(json.dumps(value))


def test_exchange_info_requires_exactly_one_primary_symbol() -> None:
    value = json.loads(_exchange_info())

    value["symbols"] = [row for row in value["symbols"] if row["symbol"] != "BTCUSDT"]

    with pytest.raises(
        BinanceUsdMNetworkError,
        match="exactly one frozen symbol",
    ):
        parse_binance_usdm_exchange_info(json.dumps(value))


def test_exchange_info_requires_utc() -> None:
    value = json.loads(_exchange_info())

    value["timezone"] = "Etc/GMT"

    with pytest.raises(
        BinanceUsdMNetworkError,
        match="timezone does not match",
    ):
        parse_binance_usdm_exchange_info(json.dumps(value))


def test_exchange_info_requires_json_object() -> None:
    with pytest.raises(
        BinanceUsdMNetworkError,
        match="JSON object",
    ):
        parse_binance_usdm_exchange_info("[]")


def test_optional_websocket_dependency_is_loadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import abmforge_finance.study.binance_usdm_network as network

    def fake_connect(
        *args: object,
        **kwargs: object,
    ) -> object:
        return object()

    monkeypatch.setattr(
        network,
        "import_module",
        lambda name: SimpleNamespace(
            connect=fake_connect,
        ),
    )

    connect = network.load_websocket_connect()

    assert connect is fake_connect


def test_network_transport_hardening_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abmforge_finance.study.binance_usdm_network as network

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok":true}'

    def fake_urlopen(
        request: object,
        *,
        timeout: float,
    ) -> FakeResponse:
        assert timeout == 3.0
        return FakeResponse()

    monkeypatch.setattr(
        network,
        "urlopen",
        fake_urlopen,
    )

    assert (
        network._http_get_text(
            "https://example.invalid/test",
            timeout_seconds=3.0,
        )
        == '{"ok":true}'
    )


def test_network_transport_failure_is_wrapped_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abmforge_finance.study.binance_usdm_network as network

    def failing_urlopen(
        request: object,
        *,
        timeout: float,
    ) -> object:
        raise URLError("offline")

    monkeypatch.setattr(
        network,
        "urlopen",
        failing_urlopen,
    )

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="HTTP request failed",
    ):
        network._http_get_text(
            "https://example.invalid/test",
            timeout_seconds=3.0,
        )


def test_network_rejects_non_utf8_http_payload_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abmforge_finance.study.binance_usdm_network as network

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def read(self) -> bytes:
            return b"\xff"

    monkeypatch.setattr(
        network,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="not UTF-8",
    ):
        network._http_get_text(
            "https://example.invalid/test",
            timeout_seconds=3.0,
        )


def test_network_fetch_helpers_use_frozen_routes_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abmforge_finance.study.binance_usdm_network as network
    from abmforge_finance.study.binance_usdm_contract import (
        binance_usdm_empirical_contract,
    )

    contract = binance_usdm_empirical_contract()
    exchange_raw = _exchange_info()

    snapshot_raw = json.dumps(
        {
            "lastUpdateId": 100,
            "E": 1000,
            "T": 999,
            "bids": [
                ["100", "5"],
                ["99", "4"],
            ],
            "asks": [
                ["101", "6"],
                ["102", "7"],
            ],
        },
        separators=(",", ":"),
    )

    seen: list[str] = []

    def fake_get(
        url: str,
        *,
        timeout_seconds: float,
    ) -> str:
        seen.append(url)

        if url.endswith(contract.exchange_info_path):
            return exchange_raw

        return snapshot_raw

    monkeypatch.setattr(
        network,
        "_http_get_text",
        fake_get,
    )

    raw_info, preflight = network.fetch_binance_usdm_exchange_info(
        timeout_seconds=7.0,
        contract=contract,
    )

    raw_snapshot, snapshot = network.fetch_binance_usdm_depth_snapshot(
        timeout_seconds=7.0,
        contract=contract,
    )

    assert raw_info == exchange_raw
    assert preflight.symbol == "BTCUSDT"

    assert raw_snapshot == snapshot_raw
    assert snapshot.last_update_id == 100

    assert seen == [
        (contract.rest_base_url + contract.exchange_info_path),
        (contract.rest_base_url + contract.depth_snapshot_path + "?symbol=BTCUSDT&limit=1000"),
    ]


def test_network_websocket_loader_failure_paths_v2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import abmforge_finance.study.binance_usdm_network as network

    def missing_module(
        name: str,
    ) -> object:
        raise ImportError(name)

    monkeypatch.setattr(
        network,
        "import_module",
        missing_module,
    )

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="optional",
    ):
        network.load_websocket_connect()

    monkeypatch.setattr(
        network,
        "import_module",
        lambda name: SimpleNamespace(connect=None),
    )

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="does not expose",
    ):
        network.load_websocket_connect()


def test_network_exchange_info_validation_edges_v2() -> None:
    import abmforge_finance.study.binance_usdm_network as network

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="non-empty JSON text",
    ):
        network.parse_binance_usdm_exchange_info("")

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="invalid JSON",
    ):
        network.parse_binance_usdm_exchange_info("{")

    value = json.loads(_exchange_info())
    value["symbols"] = "not-an-array"

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="symbols must be an array",
    ):
        network.parse_binance_usdm_exchange_info(json.dumps(value))

    value = json.loads(_exchange_info())
    value["symbols"] = [1]

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="entries must be objects",
    ):
        network.parse_binance_usdm_exchange_info(json.dumps(value))

    value = json.loads(_exchange_info())
    value["symbols"][0]["pair"] = "WRONG"

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="pair does not match",
    ):
        network.parse_binance_usdm_exchange_info(json.dumps(value))

    value = json.loads(_exchange_info())
    value["symbols"][0]["quoteAsset"] = "BTC"

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="quote asset",
    ):
        network.parse_binance_usdm_exchange_info(json.dumps(value))


def test_network_remaining_validation_edges_v4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abmforge_finance.study.binance_usdm_network as network

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="symbol must be a non-empty string",
    ):
        network.BinanceUsdMExchangePreflight(
            symbol="",
            pair="BTCUSDT",
            contract_type="PERPETUAL",
            status="TRADING",
            quote_asset="USDT",
            margin_asset="USDT",
            server_timezone="UTC",
        )

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="exchangeInfo field",
    ):
        network._required_text(
            {},
            "symbol",
        )

    value = json.loads(_exchange_info())
    value["timezone"] = ""

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="timezone must be a non-empty string",
    ):
        network.parse_binance_usdm_exchange_info(json.dumps(value))

    original_required_text = network._required_text

    from collections.abc import Mapping

    def wrong_symbol(
        payload: Mapping[str, object],
        key: str,
    ) -> str:
        if key == "symbol":
            return "ETHUSDT"

        return original_required_text(
            payload,
            key,
        )

    monkeypatch.setattr(
        network,
        "_required_text",
        wrong_symbol,
    )

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="symbol does not match",
    ):
        network.parse_binance_usdm_exchange_info(_exchange_info())


def test_network_retries_incomplete_read_v5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from http.client import IncompleteRead

    import abmforge_finance.study.binance_usdm_network as network

    calls = 0

    class BrokenResponse:
        def __enter__(self) -> BrokenResponse:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def read(self) -> bytes:
            raise IncompleteRead(
                b'{"partial":',
                100,
            )

    class GoodResponse:
        def __enter__(self) -> GoodResponse:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok":true}'

    def fake_urlopen(
        request: object,
        *,
        timeout: float,
    ) -> object:
        nonlocal calls

        calls += 1

        if calls == 1:
            return BrokenResponse()

        return GoodResponse()

    monkeypatch.setattr(
        network,
        "urlopen",
        fake_urlopen,
    )

    monkeypatch.setattr(
        "abmforge_finance.study.binance_usdm_network.time.sleep",
        lambda seconds: None,
    )

    result = network._http_get_text(
        "https://example.invalid/test",
        timeout_seconds=3.0,
    )

    assert result == '{"ok":true}'
    assert calls == 2


def test_network_exhausts_incomplete_read_retries_v5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from http.client import IncompleteRead

    import abmforge_finance.study.binance_usdm_network as network

    calls = 0

    class BrokenResponse:
        def __enter__(self) -> BrokenResponse:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def read(self) -> bytes:
            raise IncompleteRead(
                b'{"partial":',
                100,
            )

    def fake_urlopen(
        request: object,
        *,
        timeout: float,
    ) -> BrokenResponse:
        nonlocal calls
        calls += 1
        return BrokenResponse()

    monkeypatch.setattr(
        network,
        "urlopen",
        fake_urlopen,
    )

    monkeypatch.setattr(
        "abmforge_finance.study.binance_usdm_network.time.sleep",
        lambda seconds: None,
    )

    with pytest.raises(
        network.BinanceUsdMNetworkError,
        match="after 3 attempts",
    ):
        network._http_get_text(
            "https://example.invalid/test",
            timeout_seconds=3.0,
        )

    assert calls == 3
