"""Tests for typed Binance USD-M raw market-data events."""

from __future__ import annotations

from decimal import Decimal

import pytest

from abmforge_finance.exceptions import (
    InvalidMetricInputError,
    StudyProtocolError,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMAggTradeEvent,
    BinanceUsdMBookLevel,
    BinanceUsdMDepthSnapshot,
    BinanceUsdMDepthUpdateEvent,
)


def _agg_trade_payload() -> dict[str, object]:
    return {
        "e": "aggTrade",
        "E": 123456789,
        "s": "BTCUSDT",
        "a": 5933014,
        "p": "100.25",
        "q": "3.50",
        "nq": "3.25",
        "f": 100,
        "l": 105,
        "T": 123456785,
        "m": True,
        "st": 1,
    }


def _depth_payload() -> dict[str, object]:
    return {
        "e": "depthUpdate",
        "E": 123456789,
        "T": 123456788,
        "s": "BTCUSDT",
        "U": 157,
        "u": 160,
        "pu": 149,
        "b": [
            ["100.00", "2.5"],
            ["99.50", "0"],
        ],
        "a": [
            ["100.50", "3.0"],
        ],
        "ps": "BTCUSDT",
        "st": 1,
    }


def _snapshot_payload() -> dict[str, object]:
    return {
        "lastUpdateId": 160,
        "E": 123456790,
        "T": 123456789,
        "bids": [
            ["100.00", "2.5"],
            ["99.50", "4.0"],
        ],
        "asks": [
            ["100.50", "3.0"],
            ["101.00", "5.0"],
        ],
    }


def test_book_level_preserves_decimal_precision() -> None:
    level = BinanceUsdMBookLevel(
        price=Decimal("12345.67890123"),
        quantity=Decimal("0.00000017"),
    )

    assert level.price == Decimal("12345.67890123")
    assert level.quantity == Decimal("0.00000017")


def test_agg_trade_parser_preserves_official_fields() -> None:
    event = BinanceUsdMAggTradeEvent.from_mapping(_agg_trade_payload())

    assert event.event_time_ms == 123456789
    assert event.trade_time_ms == 123456785
    assert event.symbol == "BTCUSDT"
    assert event.symbol_type == 1
    assert event.aggregate_trade_id == 5933014
    assert event.price == Decimal("100.25")
    assert event.quantity == Decimal("3.50")
    assert event.normal_quantity == Decimal("3.25")
    assert event.first_trade_id == 100
    assert event.last_trade_id == 105
    assert event.buyer_is_maker is True


def test_buyer_maker_true_is_sell_aggressor() -> None:
    event = BinanceUsdMAggTradeEvent.from_mapping(_agg_trade_payload())

    assert event.aggressor_sign == -1
    assert event.signed_normal_quantity == Decimal("-3.25")


def test_buyer_maker_false_is_buy_aggressor() -> None:
    payload = _agg_trade_payload()
    payload["m"] = False

    event = BinanceUsdMAggTradeEvent.from_mapping(payload)

    assert event.aggressor_sign == 1
    assert event.signed_normal_quantity == Decimal("3.25")


def test_agg_trade_allows_zero_normal_quantity() -> None:
    payload = _agg_trade_payload()
    payload["nq"] = "0"

    event = BinanceUsdMAggTradeEvent.from_mapping(payload)

    assert event.normal_quantity == Decimal("0")
    assert event.signed_normal_quantity == Decimal("0")


def test_agg_trade_rejects_nq_above_total_quantity() -> None:
    payload = _agg_trade_payload()
    payload["nq"] = "4.0"

    with pytest.raises(
        InvalidMetricInputError,
        match="cannot exceed total quantity",
    ):
        BinanceUsdMAggTradeEvent.from_mapping(payload)


def test_agg_trade_rejects_wrong_symbol_type() -> None:
    payload = _agg_trade_payload()
    payload["st"] = 2

    with pytest.raises(
        StudyProtocolError,
        match="symbol type",
    ):
        BinanceUsdMAggTradeEvent.from_mapping(payload)


def test_agg_trade_rejects_wrong_symbol() -> None:
    payload = _agg_trade_payload()
    payload["s"] = "ETHUSDT"

    with pytest.raises(
        StudyProtocolError,
        match="symbol",
    ):
        BinanceUsdMAggTradeEvent.from_mapping(payload)


def test_agg_trade_rejects_wrong_event_type() -> None:
    payload = _agg_trade_payload()
    payload["e"] = "trade"

    with pytest.raises(
        InvalidMetricInputError,
        match="must be aggTrade",
    ):
        BinanceUsdMAggTradeEvent.from_mapping(payload)


def test_depth_parser_preserves_sequence_identity_and_levels() -> None:
    event = BinanceUsdMDepthUpdateEvent.from_mapping(_depth_payload())

    assert event.first_update_id == 157
    assert event.final_update_id == 160
    assert event.previous_final_update_id == 149
    assert event.symbol == "BTCUSDT"
    assert event.pair == "BTCUSDT"
    assert event.symbol_type == 1

    assert event.bid_updates == (
        BinanceUsdMBookLevel(
            Decimal("100.00"),
            Decimal("2.5"),
        ),
        BinanceUsdMBookLevel(
            Decimal("99.50"),
            Decimal("0"),
        ),
    )

    assert event.ask_updates == (
        BinanceUsdMBookLevel(
            Decimal("100.50"),
            Decimal("3.0"),
        ),
    )


def test_depth_update_preserves_zero_quantity_removal() -> None:
    event = BinanceUsdMDepthUpdateEvent.from_mapping(_depth_payload())

    assert event.bid_updates[1].quantity == 0


def test_depth_update_rejects_inverted_update_range() -> None:
    payload = _depth_payload()
    payload["U"] = 161
    payload["u"] = 160

    with pytest.raises(
        InvalidMetricInputError,
        match="must not exceed final_update_id",
    ):
        BinanceUsdMDepthUpdateEvent.from_mapping(payload)


def test_depth_update_rejects_wrong_pair() -> None:
    payload = _depth_payload()
    payload["ps"] = "ETHUSDT"

    with pytest.raises(
        StudyProtocolError,
        match="pair",
    ):
        BinanceUsdMDepthUpdateEvent.from_mapping(payload)


def test_depth_update_rejects_missing_required_field() -> None:
    payload = _depth_payload()
    del payload["pu"]

    with pytest.raises(
        InvalidMetricInputError,
        match="missing required field",
    ):
        BinanceUsdMDepthUpdateEvent.from_mapping(payload)


def test_snapshot_parser_preserves_rest_book() -> None:
    snapshot = BinanceUsdMDepthSnapshot.from_mapping(_snapshot_payload())

    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.last_update_id == 160

    assert snapshot.bids[0] == BinanceUsdMBookLevel(
        Decimal("100.00"),
        Decimal("2.5"),
    )
    assert snapshot.asks[0] == BinanceUsdMBookLevel(
        Decimal("100.50"),
        Decimal("3.0"),
    )


def test_snapshot_rejects_zero_quantity_level() -> None:
    payload = _snapshot_payload()
    payload["bids"] = [["100.00", "0"]]

    with pytest.raises(
        InvalidMetricInputError,
        match="snapshot quantity must be positive",
    ):
        BinanceUsdMDepthSnapshot.from_mapping(payload)


def test_snapshot_rejects_crossed_or_locked_book() -> None:
    payload = _snapshot_payload()
    payload["asks"] = [["100.00", "3.0"]]

    with pytest.raises(
        InvalidMetricInputError,
        match="positive bid-ask spread",
    ):
        BinanceUsdMDepthSnapshot.from_mapping(payload)


def test_decimal_parser_rejects_non_string_price() -> None:
    payload = _agg_trade_payload()
    payload["p"] = 100.25

    with pytest.raises(
        InvalidMetricInputError,
        match="decimal string",
    ):
        BinanceUsdMAggTradeEvent.from_mapping(payload)


def test_book_level_rejects_negative_quantity() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="non-negative and finite",
    ):
        BinanceUsdMBookLevel(
            price=Decimal("100"),
            quantity=Decimal("-1"),
        )
