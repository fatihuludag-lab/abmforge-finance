"""Tests for Binance USD-M network preflight and REST parsing."""

from __future__ import annotations

import json

import pytest

from abmforge_finance.study.binance_usdm_network import (
    BinanceUsdMNetworkError,
    load_websocket_connect,
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


def test_optional_websocket_dependency_is_loadable() -> None:
    connect = load_websocket_connect()

    assert callable(connect)
