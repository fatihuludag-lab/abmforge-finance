"""Validity-first Binance USD-M empirical reference-block construction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.binance_usdm_contract import (
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.stylized_empirical import (
    EmpiricalMarketInterval,
    prepare_empirical_market_signature_sample,
)
from abmforge_finance.study.stylized_pipeline import (
    PreparedMarketSignatureSample,
)


class BinanceUsdMEmpiricalBlockStatus(str, Enum):
    """Scientific validity status of one candidate empirical block."""

    VALID = "valid"
    REJECTED = "rejected"


class BinanceUsdMEmpiricalBlockRejectionReason(str, Enum):
    """Prespecified source-independent block rejection categories."""

    SOURCE_INTEGRITY_FAILURE = "source-integrity-failure"
    WRONG_INTERVAL_COUNT = "wrong-interval-count"
    MISALIGNED_START = "misaligned-start"
    WRONG_INTERVAL_WIDTH = "wrong-interval-width"
    CANONICAL_PREPARATION_FAILURE = "canonical-preparation-failure"


def _non_empty_text(
    value: object,
    *,
    label: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidMetricInputError(f"{label} must be a non-empty string")

    return value.strip()


def _validate_interval_container(
    intervals: object,
) -> tuple[EmpiricalMarketInterval, ...]:
    if not isinstance(intervals, tuple):
        raise TypeError("intervals must be a tuple of EmpiricalMarketInterval")

    for index, interval in enumerate(intervals):
        if not isinstance(
            interval,
            EmpiricalMarketInterval,
        ):
            raise TypeError(f"intervals[{index}] must be an EmpiricalMarketInterval")

    return intervals


@dataclass(frozen=True, slots=True)
class BinanceUsdMEmpiricalBlockResult:
    """Validity and preparation result for one candidate reference block."""

    candidate_id: str
    source_id: str
    status: BinanceUsdMEmpiricalBlockStatus

    rejection_reason: BinanceUsdMEmpiricalBlockRejectionReason | None
    rejection_detail: str | None

    raw_interval_count: int
    canonical_observation_count: int

    raw_start_timestamp_ns: int | None
    raw_end_timestamp_ns: int | None

    analysis_start_timestamp_ns: int | None
    analysis_end_timestamp_ns: int | None

    prepared_sample: PreparedMarketSignatureSample | None

    def __post_init__(self) -> None:
        _non_empty_text(
            self.candidate_id,
            label="candidate_id",
        )
        _non_empty_text(
            self.source_id,
            label="source_id",
        )

        if not isinstance(
            self.status,
            BinanceUsdMEmpiricalBlockStatus,
        ):
            raise TypeError("status must be a BinanceUsdMEmpiricalBlockStatus")

        if (
            isinstance(self.raw_interval_count, bool)
            or not isinstance(self.raw_interval_count, int)
            or self.raw_interval_count < 0
        ):
            raise InvalidMetricInputError("raw_interval_count must be a non-negative integer")

        if (
            isinstance(
                self.canonical_observation_count,
                bool,
            )
            or not isinstance(
                self.canonical_observation_count,
                int,
            )
            or self.canonical_observation_count < 0
        ):
            raise InvalidMetricInputError(
                "canonical_observation_count must be a non-negative integer"
            )

        if self.status is BinanceUsdMEmpiricalBlockStatus.VALID:
            if self.rejection_reason is not None:
                raise InvalidMetricInputError(
                    "valid empirical block cannot have a rejection reason"
                )

            if self.rejection_detail is not None:
                raise InvalidMetricInputError("valid empirical block cannot have rejection detail")

            if self.prepared_sample is None:
                raise InvalidMetricInputError(
                    "valid empirical block must contain a prepared sample"
                )

            if self.analysis_start_timestamp_ns is None or self.analysis_end_timestamp_ns is None:
                raise InvalidMetricInputError(
                    "valid empirical block must contain analysis timestamps"
                )

            if self.prepared_sample.data.observation_count != self.canonical_observation_count:
                raise InvalidMetricInputError(
                    "canonical observation count must match the prepared sample"
                )

        else:
            if self.rejection_reason is None:
                raise InvalidMetricInputError(
                    "rejected empirical block must have a rejection reason"
                )

            if self.rejection_detail is None or not self.rejection_detail:
                raise InvalidMetricInputError("rejected empirical block must have rejection detail")

            if self.prepared_sample is not None:
                raise InvalidMetricInputError(
                    "rejected empirical block cannot contain a prepared sample"
                )

            if self.canonical_observation_count != 0:
                raise InvalidMetricInputError(
                    "rejected empirical block must have zero canonical observations"
                )

            if (
                self.analysis_start_timestamp_ns is not None
                or self.analysis_end_timestamp_ns is not None
            ):
                raise InvalidMetricInputError(
                    "rejected empirical block cannot expose analysis timestamps"
                )

    @property
    def is_valid(self) -> bool:
        """Return whether the candidate is scientifically valid."""

        return self.status is BinanceUsdMEmpiricalBlockStatus.VALID


def _raw_bounds(
    intervals: tuple[EmpiricalMarketInterval, ...],
) -> tuple[int | None, int | None]:
    if not intervals:
        return None, None

    return (
        intervals[0].start_timestamp_ns,
        intervals[-1].end_timestamp_ns,
    )


def _rejected(
    *,
    candidate_id: str,
    source_id: str,
    intervals: tuple[EmpiricalMarketInterval, ...],
    reason: BinanceUsdMEmpiricalBlockRejectionReason,
    detail: str,
) -> BinanceUsdMEmpiricalBlockResult:
    raw_start, raw_end = _raw_bounds(intervals)

    return BinanceUsdMEmpiricalBlockResult(
        candidate_id=candidate_id,
        source_id=source_id,
        status=BinanceUsdMEmpiricalBlockStatus.REJECTED,
        rejection_reason=reason,
        rejection_detail=detail,
        raw_interval_count=len(intervals),
        canonical_observation_count=0,
        raw_start_timestamp_ns=raw_start,
        raw_end_timestamp_ns=raw_end,
        analysis_start_timestamp_ns=None,
        analysis_end_timestamp_ns=None,
        prepared_sample=None,
    )


def evaluate_binance_usdm_empirical_block(
    *,
    candidate_id: str,
    source_id: str,
    intervals: tuple[EmpiricalMarketInterval, ...],
    source_integrity_failure: str | None = None,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> BinanceUsdMEmpiricalBlockResult:
    """Evaluate block validity without inspecting stylized-fact estimates."""

    candidate = _non_empty_text(
        candidate_id,
        label="candidate_id",
    )
    source = _non_empty_text(
        source_id,
        label="source_id",
    )

    rows = _validate_interval_container(intervals)

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    if source_integrity_failure is not None:
        detail = _non_empty_text(
            source_integrity_failure,
            label="source_integrity_failure",
        )

        return _rejected(
            candidate_id=candidate,
            source_id=source,
            intervals=rows,
            reason=(BinanceUsdMEmpiricalBlockRejectionReason.SOURCE_INTEGRITY_FAILURE),
            detail=detail,
        )

    expected_interval_count = active_contract.block_observation_count + 1

    if len(rows) != expected_interval_count:
        return _rejected(
            candidate_id=candidate,
            source_id=source,
            intervals=rows,
            reason=(BinanceUsdMEmpiricalBlockRejectionReason.WRONG_INTERVAL_COUNT),
            detail=(
                "candidate must contain exactly "
                f"{expected_interval_count} empirical intervals "
                "to produce "
                f"{active_contract.block_observation_count} "
                "canonical observations"
            ),
        )

    first = rows[0]

    if first.start_timestamp_ns % active_contract.interval_ns != 0:
        return _rejected(
            candidate_id=candidate,
            source_id=source,
            intervals=rows,
            reason=(BinanceUsdMEmpiricalBlockRejectionReason.MISALIGNED_START),
            detail=("candidate raw window must begin on a UTC-second boundary"),
        )

    for index, interval in enumerate(rows):
        width = interval.end_timestamp_ns - interval.start_timestamp_ns

        if width != active_contract.interval_ns:
            return _rejected(
                candidate_id=candidate,
                source_id=source,
                intervals=rows,
                reason=(BinanceUsdMEmpiricalBlockRejectionReason.WRONG_INTERVAL_WIDTH),
                detail=(f"interval {index} width does not match the frozen one-second contract"),
            )

    try:
        sample = prepare_empirical_market_signature_sample(
            rows,
            source_id=source,
        )
    except InvalidMetricInputError as exc:
        return _rejected(
            candidate_id=candidate,
            source_id=source,
            intervals=rows,
            reason=(BinanceUsdMEmpiricalBlockRejectionReason.CANONICAL_PREPARATION_FAILURE),
            detail=str(exc),
        )

    if sample.data.observation_count != active_contract.block_observation_count:
        return _rejected(
            candidate_id=candidate,
            source_id=source,
            intervals=rows,
            reason=(BinanceUsdMEmpiricalBlockRejectionReason.CANONICAL_PREPARATION_FAILURE),
            detail=(
                "prepared sample observation count does not "
                "match the frozen empirical block horizon"
            ),
        )

    raw_start, raw_end = _raw_bounds(rows)

    return BinanceUsdMEmpiricalBlockResult(
        candidate_id=candidate,
        source_id=source,
        status=BinanceUsdMEmpiricalBlockStatus.VALID,
        rejection_reason=None,
        rejection_detail=None,
        raw_interval_count=len(rows),
        canonical_observation_count=(sample.data.observation_count),
        raw_start_timestamp_ns=raw_start,
        raw_end_timestamp_ns=raw_end,
        analysis_start_timestamp_ns=(rows[1].start_timestamp_ns),
        analysis_end_timestamp_ns=(rows[-1].end_timestamp_ns),
        prepared_sample=sample,
    )
