"""Tests for the frozen Binance USD-M empirical source contract."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study.binance_usdm_contract import (
    BINANCE_USDM_EMPIRICAL_CONTRACT_ID,
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.stylized_protocol import (
    stylized_fact_validation_protocol,
)


def _contract() -> BinanceUsdMEmpiricalContract:
    return binance_usdm_empirical_contract()


def test_contract_freezes_primary_market_identity() -> None:
    contract = _contract()

    assert contract.contract_id == BINANCE_USDM_EMPIRICAL_CONTRACT_ID
    assert contract.venue == "binance"
    assert contract.market_family == "usds-m-futures"
    assert contract.symbol == "BTCUSDT"
    assert contract.pair == "BTCUSDT"
    assert contract.contract_type == "PERPETUAL"
    assert contract.trading_status == "TRADING"
    assert contract.quote_asset == "USDT"
    assert contract.margin_asset == "USDT"
    assert contract.required_symbol_type == 1
    assert contract.timezone == "UTC"


def test_contract_matches_frozen_analysis_horizon() -> None:
    contract = _contract()
    protocol = stylized_fact_validation_protocol()

    assert contract.block_observation_count == protocol.analysis_horizon == 4096
    assert contract.reference_block_count == 64
    assert contract.reference_observation_count == 262_144
    assert contract.block_duration_seconds == 4096
    assert contract.reference_duration_seconds == 262_144


def test_contract_uses_current_routed_websocket_topology() -> None:
    contract = _contract()

    assert contract.depth_route == "public"
    assert contract.depth_update_speed == "100ms"
    assert contract.aggregate_trade_route == "market"
    assert contract.aggregate_trade_update_speed_ms == 100

    assert contract.depth_websocket_url == (
        "wss://fstream.binance.com/public/ws/btcusdt@depth@100ms"
    )

    assert contract.aggregate_trade_websocket_url == (
        "wss://fstream.binance.com/market/ws/btcusdt@aggTrade"
    )


def test_contract_aligns_non_rpi_flow_and_depth() -> None:
    contract = _contract()

    assert contract.depth_rpi_included is False
    assert contract.aggregate_trade_quantity_field == "nq"
    assert contract.aggregate_trade_buyer_maker_field == "m"
    assert contract.aggregate_trade_symbol_type_field == "st"
    assert contract.required_symbol_type == 1
    assert contract.no_trade_flow_value == 0.0


def test_contract_freezes_local_book_synchronization() -> None:
    contract = _contract()

    assert contract.depth_snapshot_limit == 1000
    assert contract.depth_first_event_rule == ("U<=lastUpdateId<=u")
    assert contract.depth_continuity_rule == ("pu==previous_u")
    assert contract.depth_update_quantity_semantics == ("absolute")
    assert contract.zero_depth_quantity_action == ("remove-level")
    assert contract.depth_gap_policy == ("invalidate-block-resync-book")
    assert contract.reconnect_policy == ("resync-book-start-new-block")


def test_contract_freezes_empirical_measurement_boundary() -> None:
    contract = _contract()

    assert contract.interval_ns == 1_000_000_000
    assert contract.clock_alignment == ("utc-second-boundary")
    assert contract.interval_close_state_rule == ("last-synchronized-book-state-in-interval")
    assert contract.depth_measurement == ("sum-maintained-non-rpi-local-book-quantity-per-side")


def test_contract_freezes_raw_artifact_policy() -> None:
    contract = _contract()

    assert contract.raw_event_format == "jsonl"
    assert contract.hash_algorithm == "sha256"


def test_contract_mapping_is_deterministic_and_json_serializable() -> None:
    first = _contract().to_mapping()
    second = _contract().to_mapping()

    assert first == second

    first_json = json.dumps(
        first,
        sort_keys=True,
        separators=(",", ":"),
    )
    second_json = json.dumps(
        second,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert first_json == second_json


def test_contract_is_immutable() -> None:
    contract = _contract()

    with pytest.raises(FrozenInstanceError):
        contract.symbol = "ETHUSDT"  # type: ignore[misc]


def test_contract_rejects_total_quantity_for_official_flow() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="must use nq",
    ):
        replace(
            _contract(),
            aggregate_trade_quantity_field="q",
        )


def test_contract_rejects_wrong_depth_route() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="public route",
    ):
        replace(
            _contract(),
            depth_route="market",
        )


def test_contract_rejects_wrong_trade_route() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="market route",
    ):
        replace(
            _contract(),
            aggregate_trade_route="public",
        )


def test_contract_rejects_smaller_depth_snapshot() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="limit must be 1000",
    ):
        replace(
            _contract(),
            depth_snapshot_limit=500,
        )


def test_contract_rejects_wrong_block_horizon() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="4096 observations",
    ):
        replace(
            _contract(),
            block_observation_count=2048,
        )


def test_contract_rejects_wrong_reference_block_count() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="64 valid blocks",
    ):
        replace(
            _contract(),
            reference_block_count=32,
        )


def test_contract_rejects_wrong_symbol_type() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="USD-M as 1",
    ):
        replace(
            _contract(),
            required_symbol_type=2,
        )


def test_contract_rejects_rpi_inclusive_depth() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="exclude RPI",
    ):
        replace(
            _contract(),
            depth_rpi_included=True,
        )


def test_contract_rejects_wrong_depth_update_speed() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="depth update speed must be 100ms",
    ):
        replace(
            _contract(),
            depth_update_speed="500ms",
            depth_stream="btcusdt@depth@500ms",
        )


def test_contract_rejects_wrong_aggregate_trade_update_speed() -> None:
    with pytest.raises(
        StudyProtocolError,
        match="aggregate-trade update speed must be 100ms",
    ):
        replace(
            _contract(),
            aggregate_trade_update_speed_ms=250,
        )


@pytest.mark.parametrize(
    ("field", "replacement_value", "message"),
    (
        ("contract_id", "wrong", "contract id"),
        ("venue", "other", "venue"),
        ("market_family", "spot", "market_family"),
        ("symbol", "btcusdt", "uppercase"),
        ("pair", "ETHUSDT", "pair"),
        ("contract_type", "CURRENT_QUARTER", "PERPETUAL"),
        ("trading_status", "BREAK", "TRADING"),
        ("quote_asset", "BTC", "quote_asset"),
        ("margin_asset", "BTC", "margin_asset"),
        ("timezone", "Europe/Istanbul", "UTC"),
        ("interval_ns", 2_000_000_000, "one second"),
        (
            "websocket_base_url",
            "wss://example.invalid",
            "WebSocket base URL",
        ),
        (
            "depth_stream",
            "ethusdt@depth@100ms",
            "depth stream",
        ),
        (
            "aggregate_trade_stream",
            "ethusdt@aggTrade",
            "aggregate-trade stream",
        ),
        (
            "rest_base_url",
            "https://example.invalid",
            "REST base URL",
        ),
        (
            "exchange_info_path",
            "/wrong",
            "exchange-info path",
        ),
        (
            "depth_snapshot_path",
            "/wrong",
            "depth-snapshot path",
        ),
        (
            "aggregate_trade_buyer_maker_field",
            "wrong",
            "buyer-maker field",
        ),
        (
            "aggregate_trade_symbol_type_field",
            "wrong",
            "symbol-type field",
        ),
        (
            "no_trade_flow_value",
            1.0,
            "no-trade flow",
        ),
        (
            "depth_first_event_rule",
            "wrong",
            "first depth-event",
        ),
        (
            "depth_continuity_rule",
            "wrong",
            "depth continuity",
        ),
        (
            "depth_update_quantity_semantics",
            "delta",
            "absolute semantics",
        ),
        (
            "zero_depth_quantity_action",
            "retain",
            "remove the price level",
        ),
        (
            "depth_measurement",
            "wrong",
            "depth measurement",
        ),
        (
            "clock_alignment",
            "local-clock",
            "UTC-second aligned",
        ),
        (
            "interval_close_state_rule",
            "wrong",
            "interval-closing",
        ),
        (
            "depth_gap_policy",
            "ignore",
            "depth-gap policy",
        ),
        (
            "reconnect_policy",
            "continue",
            "reconnect policy",
        ),
        (
            "raw_event_format",
            "csv",
            "jsonl",
        ),
        (
            "hash_algorithm",
            "md5",
            "sha256",
        ),
    ),
)
def test_frozen_contract_rejects_protocol_drift_v2(
    field: str,
    replacement_value: object,
    message: str,
) -> None:
    from dataclasses import replace
    from typing import Any, cast

    from abmforge_finance.exceptions import StudyProtocolError
    from abmforge_finance.study.binance_usdm_contract import (
        binance_usdm_empirical_contract,
    )

    contract = binance_usdm_empirical_contract()

    with pytest.raises(
        StudyProtocolError,
        match=message,
    ):
        replace_any = cast(Any, replace)
        replace_any(
            contract,
            **{field: replacement_value},
        )
