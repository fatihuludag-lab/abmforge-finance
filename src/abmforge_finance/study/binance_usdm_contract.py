"""Frozen Binance USD-M empirical source contract for Phase 11."""

from __future__ import annotations

from dataclasses import dataclass

from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study.stylized_protocol import (
    stylized_fact_validation_protocol,
)

BINANCE_USDM_EMPIRICAL_CONTRACT_ID = "binance-usdm-btcusdt-empirical-v1"

_REFERENCE_BLOCK_COUNT = 64
_INTERVAL_NS = 1_000_000_000


@dataclass(frozen=True, slots=True)
class BinanceUsdMEmpiricalContract:
    """Prespecified Binance USD-M source and collection semantics."""

    contract_id: str
    venue: str
    market_family: str
    symbol: str
    pair: str
    contract_type: str
    trading_status: str
    quote_asset: str
    margin_asset: str
    required_symbol_type: int
    timezone: str

    interval_ns: int
    block_observation_count: int
    reference_block_count: int

    websocket_base_url: str
    depth_route: str
    aggregate_trade_route: str
    depth_stream: str
    depth_update_speed: str
    aggregate_trade_stream: str

    aggregate_trade_update_speed_ms: int
    rest_base_url: str
    exchange_info_path: str
    depth_snapshot_path: str
    depth_snapshot_limit: int

    depth_rpi_included: bool
    aggregate_trade_quantity_field: str
    aggregate_trade_buyer_maker_field: str
    aggregate_trade_symbol_type_field: str
    no_trade_flow_value: float

    depth_first_event_rule: str
    depth_continuity_rule: str
    depth_update_quantity_semantics: str
    zero_depth_quantity_action: str

    depth_measurement: str
    clock_alignment: str
    interval_close_state_rule: str

    depth_gap_policy: str
    reconnect_policy: str

    raw_event_format: str
    hash_algorithm: str

    def __post_init__(self) -> None:
        if self.contract_id != BINANCE_USDM_EMPIRICAL_CONTRACT_ID:
            raise StudyProtocolError("unexpected Binance empirical contract id")

        if self.venue != "binance":
            raise StudyProtocolError("Binance empirical venue must be binance")

        if self.market_family != "usds-m-futures":
            raise StudyProtocolError("market_family must be usds-m-futures")

        if self.symbol != self.symbol.upper():
            raise StudyProtocolError("Binance empirical symbol must be uppercase")

        if self.pair != self.symbol:
            raise StudyProtocolError("primary empirical pair must match symbol")

        if self.contract_type != "PERPETUAL":
            raise StudyProtocolError("contract_type must be PERPETUAL")

        if self.trading_status != "TRADING":
            raise StudyProtocolError("trading_status must be TRADING")

        if self.quote_asset != "USDT":
            raise StudyProtocolError("quote_asset must be USDT")

        if self.margin_asset != "USDT":
            raise StudyProtocolError("margin_asset must be USDT")

        if self.required_symbol_type != 1:
            raise StudyProtocolError("required_symbol_type must identify USD-M as 1")

        if self.timezone != "UTC":
            raise StudyProtocolError("empirical timezone must be UTC")

        if self.interval_ns != _INTERVAL_NS:
            raise StudyProtocolError("empirical interval must be one second")

        if self.block_observation_count != 4096:
            raise StudyProtocolError("empirical block must contain 4096 observations")

        if self.reference_block_count != _REFERENCE_BLOCK_COUNT:
            raise StudyProtocolError("empirical reference must contain 64 valid blocks")

        if self.websocket_base_url != "wss://fstream.binance.com":
            raise StudyProtocolError("unexpected Binance Futures WebSocket base URL")

        if self.depth_route != "public":
            raise StudyProtocolError("depth stream must use the public route")

        if self.aggregate_trade_route != "market":
            raise StudyProtocolError("aggregate-trade stream must use the market route")

        if self.depth_update_speed != "100ms":
            raise StudyProtocolError("depth update speed must be 100ms")

        expected_depth_stream = f"{self.symbol.lower()}@depth@{self.depth_update_speed}"
        if self.depth_stream != expected_depth_stream:
            raise StudyProtocolError("depth stream must match the frozen symbol")

        if self.aggregate_trade_update_speed_ms != 100:
            raise StudyProtocolError("aggregate-trade update speed must be 100ms")

        expected_trade_stream = f"{self.symbol.lower()}@aggTrade"
        if self.aggregate_trade_stream != expected_trade_stream:
            raise StudyProtocolError("aggregate-trade stream must match the frozen symbol")

        if self.rest_base_url != "https://fapi.binance.com":
            raise StudyProtocolError("unexpected Binance Futures REST base URL")

        if self.exchange_info_path != "/fapi/v1/exchangeInfo":
            raise StudyProtocolError("unexpected exchange-info path")

        if self.depth_snapshot_path != "/fapi/v1/depth":
            raise StudyProtocolError("unexpected depth-snapshot path")

        if self.depth_snapshot_limit != 1000:
            raise StudyProtocolError("depth snapshot limit must be 1000")

        if self.depth_rpi_included:
            raise StudyProtocolError("standard empirical depth must exclude RPI")

        if self.aggregate_trade_quantity_field != "nq":
            raise StudyProtocolError("empirical aggressor flow must use nq")

        if self.aggregate_trade_buyer_maker_field != "m":
            raise StudyProtocolError("aggressor direction must use buyer-maker field m")

        if self.aggregate_trade_symbol_type_field != "st":
            raise StudyProtocolError("USD-M stream validation must use symbol-type field st")

        if self.no_trade_flow_value != 0.0:
            raise StudyProtocolError("observed no-trade flow must equal zero")

        if self.depth_first_event_rule != "U<=lastUpdateId<=u":
            raise StudyProtocolError("unexpected first depth-event synchronization rule")

        if self.depth_continuity_rule != "pu==previous_u":
            raise StudyProtocolError("unexpected depth continuity rule")

        if self.depth_update_quantity_semantics != "absolute":
            raise StudyProtocolError("depth quantities must use absolute semantics")

        if self.zero_depth_quantity_action != "remove-level":
            raise StudyProtocolError("zero depth quantity must remove the price level")

        if self.depth_measurement != ("sum-maintained-non-rpi-local-book-quantity-per-side"):
            raise StudyProtocolError("unexpected empirical depth measurement")

        if self.clock_alignment != "utc-second-boundary":
            raise StudyProtocolError("empirical intervals must be UTC-second aligned")

        if self.interval_close_state_rule != ("last-synchronized-book-state-in-interval"):
            raise StudyProtocolError("unexpected interval-closing book-state rule")

        if self.depth_gap_policy != "invalidate-block-resync-book":
            raise StudyProtocolError("unexpected depth-gap policy")

        if self.reconnect_policy != "resync-book-start-new-block":
            raise StudyProtocolError("unexpected reconnect policy")

        if self.raw_event_format != "jsonl":
            raise StudyProtocolError("raw empirical event format must be jsonl")

        if self.hash_algorithm != "sha256":
            raise StudyProtocolError("empirical artifact hash algorithm must be sha256")

    @property
    def depth_websocket_url(self) -> str:
        """Return the routed depth-stream URL."""

        return f"{self.websocket_base_url}/{self.depth_route}/ws/{self.depth_stream}"

    @property
    def aggregate_trade_websocket_url(self) -> str:
        """Return the routed aggregate-trade URL."""

        return (
            f"{self.websocket_base_url}/"
            f"{self.aggregate_trade_route}/ws/"
            f"{self.aggregate_trade_stream}"
        )

    @property
    def reference_observation_count(self) -> int:
        """Return total canonical observations in the reference set."""

        return self.block_observation_count * self.reference_block_count

    @property
    def block_duration_seconds(self) -> int:
        """Return physical duration of one complete empirical block."""

        return self.block_observation_count * self.interval_ns // 1_000_000_000

    @property
    def reference_duration_seconds(self) -> int:
        """Return minimum valid physical duration in the reference set."""

        return self.block_duration_seconds * self.reference_block_count

    def to_mapping(self) -> dict[str, object]:
        """Return a deterministic machine-readable contract mapping."""

        return {
            "aggregate_trade_buyer_maker_field": (self.aggregate_trade_buyer_maker_field),
            "aggregate_trade_quantity_field": (self.aggregate_trade_quantity_field),
            "aggregate_trade_route": self.aggregate_trade_route,
            "aggregate_trade_stream": self.aggregate_trade_stream,
            "aggregate_trade_update_speed_ms": (self.aggregate_trade_update_speed_ms),
            "aggregate_trade_symbol_type_field": (self.aggregate_trade_symbol_type_field),
            "block_observation_count": self.block_observation_count,
            "clock_alignment": self.clock_alignment,
            "contract_id": self.contract_id,
            "contract_type": self.contract_type,
            "depth_continuity_rule": self.depth_continuity_rule,
            "depth_first_event_rule": self.depth_first_event_rule,
            "depth_gap_policy": self.depth_gap_policy,
            "depth_measurement": self.depth_measurement,
            "depth_route": self.depth_route,
            "depth_rpi_included": self.depth_rpi_included,
            "depth_snapshot_limit": self.depth_snapshot_limit,
            "depth_snapshot_path": self.depth_snapshot_path,
            "depth_stream": self.depth_stream,
            "depth_update_speed": self.depth_update_speed,
            "depth_update_quantity_semantics": (self.depth_update_quantity_semantics),
            "hash_algorithm": self.hash_algorithm,
            "interval_close_state_rule": self.interval_close_state_rule,
            "interval_ns": self.interval_ns,
            "margin_asset": self.margin_asset,
            "market_family": self.market_family,
            "no_trade_flow_value": self.no_trade_flow_value,
            "pair": self.pair,
            "quote_asset": self.quote_asset,
            "raw_event_format": self.raw_event_format,
            "reconnect_policy": self.reconnect_policy,
            "reference_block_count": self.reference_block_count,
            "required_symbol_type": self.required_symbol_type,
            "rest_base_url": self.rest_base_url,
            "symbol": self.symbol,
            "timezone": self.timezone,
            "trading_status": self.trading_status,
            "venue": self.venue,
            "websocket_base_url": self.websocket_base_url,
            "zero_depth_quantity_action": (self.zero_depth_quantity_action),
        }


def binance_usdm_empirical_contract() -> BinanceUsdMEmpiricalContract:
    """Return the frozen primary Binance USD-M Phase 11 contract."""

    protocol = stylized_fact_validation_protocol()

    return BinanceUsdMEmpiricalContract(
        contract_id=BINANCE_USDM_EMPIRICAL_CONTRACT_ID,
        venue="binance",
        market_family="usds-m-futures",
        symbol="BTCUSDT",
        pair="BTCUSDT",
        contract_type="PERPETUAL",
        trading_status="TRADING",
        quote_asset="USDT",
        margin_asset="USDT",
        required_symbol_type=1,
        timezone="UTC",
        interval_ns=_INTERVAL_NS,
        block_observation_count=protocol.analysis_horizon,
        reference_block_count=_REFERENCE_BLOCK_COUNT,
        websocket_base_url="wss://fstream.binance.com",
        depth_route="public",
        aggregate_trade_route="market",
        depth_stream="btcusdt@depth@100ms",
        depth_update_speed="100ms",
        aggregate_trade_stream="btcusdt@aggTrade",
        aggregate_trade_update_speed_ms=100,
        rest_base_url="https://fapi.binance.com",
        exchange_info_path="/fapi/v1/exchangeInfo",
        depth_snapshot_path="/fapi/v1/depth",
        depth_snapshot_limit=1000,
        depth_rpi_included=False,
        aggregate_trade_quantity_field="nq",
        aggregate_trade_buyer_maker_field="m",
        aggregate_trade_symbol_type_field="st",
        no_trade_flow_value=0.0,
        depth_first_event_rule="U<=lastUpdateId<=u",
        depth_continuity_rule="pu==previous_u",
        depth_update_quantity_semantics="absolute",
        zero_depth_quantity_action="remove-level",
        depth_measurement=("sum-maintained-non-rpi-local-book-quantity-per-side"),
        clock_alignment="utc-second-boundary",
        interval_close_state_rule=("last-synchronized-book-state-in-interval"),
        depth_gap_policy="invalidate-block-resync-book",
        reconnect_policy="resync-book-start-new-block",
        raw_event_format="jsonl",
        hash_algorithm="sha256",
    )
