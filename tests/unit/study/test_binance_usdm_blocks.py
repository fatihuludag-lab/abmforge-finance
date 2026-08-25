"""Tests for Binance USD-M validity-first empirical block construction."""

from __future__ import annotations

import math

import pytest

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.binance_usdm_blocks import (
    BinanceUsdMEmpiricalBlockRejectionReason,
    BinanceUsdMEmpiricalBlockStatus,
    evaluate_binance_usdm_empirical_block,
)
from abmforge_finance.study.stylized_empirical import (
    EmpiricalMarketInterval,
)

_INTERVAL_NS = 1_000_000_000
_REQUIRED_INTERVALS = 4_097


def _intervals(
    *,
    count: int = _REQUIRED_INTERVALS,
    start_ns: int = 0,
    width_ns: int = _INTERVAL_NS,
) -> tuple[EmpiricalMarketInterval, ...]:
    return tuple(
        EmpiricalMarketInterval(
            start_timestamp_ns=(start_ns + index * width_ns),
            end_timestamp_ns=(start_ns + (index + 1) * width_ns),
            mid_price=(10_000.0 + (index % 17) * 0.25 + index * 0.001),
            aggressor_flow=(1.0 if index % 2 == 0 else -1.0),
            thin_side_depth=(10.0 + (index % 11)),
        )
        for index in range(count)
    )


def test_valid_block_uses_4097_intervals_for_4096_observations() -> None:
    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-000",
        source_id="capture-000",
        intervals=_intervals(),
    )

    assert result.status is BinanceUsdMEmpiricalBlockStatus.VALID
    assert result.is_valid is True

    assert result.raw_interval_count == 4097
    assert result.canonical_observation_count == 4096

    assert result.prepared_sample is not None
    assert result.prepared_sample.data.observation_count == 4096


def test_first_interval_is_seed_not_canonical_observation() -> None:
    rows = _intervals()

    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-seed",
        source_id="capture-seed",
        intervals=rows,
    )

    assert result.prepared_sample is not None

    expected_return = math.log(rows[1].mid_price / rows[0].mid_price)

    assert result.prepared_sample.data.log_returns[0] == pytest.approx(expected_return)

    assert result.prepared_sample.data.aggressor_flow[0] == rows[1].aggressor_flow

    assert result.prepared_sample.data.pre_interval_thin_side_depth[0] == pytest.approx(
        rows[0].thin_side_depth
    )


def test_valid_block_exposes_raw_and_analysis_boundaries() -> None:
    rows = _intervals()

    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-bounds",
        source_id="capture-bounds",
        intervals=rows,
    )

    assert result.raw_start_timestamp_ns == (rows[0].start_timestamp_ns)
    assert result.raw_end_timestamp_ns == (rows[-1].end_timestamp_ns)

    assert result.analysis_start_timestamp_ns == (rows[1].start_timestamp_ns)
    assert result.analysis_end_timestamp_ns == (rows[-1].end_timestamp_ns)

    assert (
        result.analysis_end_timestamp_ns - result.analysis_start_timestamp_ns
        == 4_096 * _INTERVAL_NS
    )


def test_wrong_interval_count_is_rejected_without_estimation() -> None:
    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-short",
        source_id="capture-short",
        intervals=_intervals(count=4096),
    )

    assert result.is_valid is False
    assert result.status is BinanceUsdMEmpiricalBlockStatus.REJECTED
    assert result.rejection_reason is (
        BinanceUsdMEmpiricalBlockRejectionReason.WRONG_INTERVAL_COUNT
    )
    assert result.canonical_observation_count == 0
    assert result.prepared_sample is None


def test_misaligned_raw_start_is_rejected() -> None:
    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-misaligned",
        source_id="capture-misaligned",
        intervals=_intervals(start_ns=1),
    )

    assert result.rejection_reason is (BinanceUsdMEmpiricalBlockRejectionReason.MISALIGNED_START)


def test_wrong_interval_width_is_rejected() -> None:
    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-width",
        source_id="capture-width",
        intervals=_intervals(
            width_ns=500_000_000,
        ),
    )

    assert result.rejection_reason is (
        BinanceUsdMEmpiricalBlockRejectionReason.WRONG_INTERVAL_WIDTH
    )


def test_source_integrity_failure_rejects_candidate_immediately() -> None:
    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-gap",
        source_id="capture-gap",
        intervals=_intervals(count=100),
        source_integrity_failure=("depth update continuity failure"),
    )

    assert result.status is BinanceUsdMEmpiricalBlockStatus.REJECTED
    assert result.rejection_reason is (
        BinanceUsdMEmpiricalBlockRejectionReason.SOURCE_INTEGRITY_FAILURE
    )
    assert result.rejection_detail == ("depth update continuity failure")
    assert result.prepared_sample is None


def test_zero_seed_depth_is_canonical_preparation_failure() -> None:
    rows = list(_intervals())

    first = rows[0]

    rows[0] = EmpiricalMarketInterval(
        start_timestamp_ns=first.start_timestamp_ns,
        end_timestamp_ns=first.end_timestamp_ns,
        mid_price=first.mid_price,
        aggressor_flow=first.aggressor_flow,
        thin_side_depth=0.0,
    )

    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-zero-depth",
        source_id="capture-zero-depth",
        intervals=tuple(rows),
    )

    assert result.rejection_reason is (
        BinanceUsdMEmpiricalBlockRejectionReason.CANONICAL_PREPARATION_FAILURE
    )

    assert result.prepared_sample is None


def test_gap_is_canonical_preparation_failure() -> None:
    rows = list(_intervals())

    target = rows[100]

    rows[100] = EmpiricalMarketInterval(
        start_timestamp_ns=(target.start_timestamp_ns + _INTERVAL_NS),
        end_timestamp_ns=(target.end_timestamp_ns + _INTERVAL_NS),
        mid_price=target.mid_price,
        aggressor_flow=target.aggressor_flow,
        thin_side_depth=target.thin_side_depth,
    )

    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-gap",
        source_id="capture-gap",
        intervals=tuple(rows),
    )

    assert result.rejection_reason is (
        BinanceUsdMEmpiricalBlockRejectionReason.CANONICAL_PREPARATION_FAILURE
    )

    assert result.rejection_detail is not None
    assert "contiguous" in result.rejection_detail


def test_validity_does_not_require_stylized_fact_estimates() -> None:
    result = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate-no-estimates",
        source_id="capture-no-estimates",
        intervals=_intervals(),
    )

    assert result.is_valid is True
    assert result.prepared_sample is not None

    # Block validity stores prepared measurements only.
    # No estimator result is part of the block validity record.
    assert not hasattr(result, "estimates")


def test_invalid_candidate_identity_is_rejected_as_input_error() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="candidate_id",
    ):
        evaluate_binance_usdm_empirical_block(
            candidate_id=" ",
            source_id="capture",
            intervals=_intervals(),
        )


def test_empty_source_integrity_failure_is_not_valid_metadata() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="source_integrity_failure",
    ):
        evaluate_binance_usdm_empirical_block(
            candidate_id="candidate",
            source_id="capture",
            intervals=_intervals(count=1),
            source_integrity_failure=" ",
        )


def test_block_container_type_guards_v3() -> None:
    from typing import cast

    from abmforge_finance.study.binance_usdm_blocks import (
        evaluate_binance_usdm_empirical_block,
    )
    from abmforge_finance.study.stylized_empirical import (
        EmpiricalMarketInterval,
    )

    with pytest.raises(
        TypeError,
        match="intervals must be a tuple",
    ):
        evaluate_binance_usdm_empirical_block(
            candidate_id="candidate",
            source_id="source",
            intervals=cast(
                tuple[EmpiricalMarketInterval, ...],
                [],
            ),
        )

    with pytest.raises(
        TypeError,
        match=r"intervals\[0\]",
    ):
        evaluate_binance_usdm_empirical_block(
            candidate_id="candidate",
            source_id="source",
            intervals=(
                cast(
                    EmpiricalMarketInterval,
                    object(),
                ),
            ),
        )


def test_valid_block_result_invariants_are_enforced_v3() -> None:
    from dataclasses import replace
    from typing import Any, cast

    from abmforge_finance.exceptions import (
        InvalidMetricInputError,
    )
    from abmforge_finance.study.binance_usdm_blocks import (
        BinanceUsdMEmpiricalBlockRejectionReason,
        BinanceUsdMEmpiricalBlockStatus,
        evaluate_binance_usdm_empirical_block,
    )

    valid = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate",
        source_id="source",
        intervals=_intervals(),
    )

    assert valid.status is BinanceUsdMEmpiricalBlockStatus.VALID
    assert valid.prepared_sample is not None

    replace_any = cast(Any, replace)

    with pytest.raises(
        TypeError,
        match="status",
    ):
        replace_any(
            valid,
            status="VALID",
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="raw_interval_count",
    ):
        replace(
            valid,
            raw_interval_count=-1,
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="canonical_observation_count",
    ):
        replace(
            valid,
            canonical_observation_count=-1,
        )

    reason = next(iter(BinanceUsdMEmpiricalBlockRejectionReason))

    with pytest.raises(
        InvalidMetricInputError,
        match="cannot have a rejection reason",
    ):
        replace(
            valid,
            rejection_reason=reason,
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="cannot have rejection detail",
    ):
        replace(
            valid,
            rejection_detail="unexpected",
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="must contain a prepared sample",
    ):
        replace(
            valid,
            prepared_sample=None,
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="analysis timestamps",
    ):
        replace(
            valid,
            analysis_start_timestamp_ns=None,
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="must match the prepared sample",
    ):
        replace(
            valid,
            canonical_observation_count=(valid.canonical_observation_count + 1),
        )


def test_rejected_block_result_invariants_are_enforced_v3() -> None:
    from dataclasses import replace

    from abmforge_finance.exceptions import (
        InvalidMetricInputError,
    )
    from abmforge_finance.study.binance_usdm_blocks import (
        BinanceUsdMEmpiricalBlockStatus,
        evaluate_binance_usdm_empirical_block,
    )

    rejected = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate",
        source_id="source",
        intervals=(),
        source_integrity_failure="source gap",
    )

    assert rejected.status is BinanceUsdMEmpiricalBlockStatus.REJECTED

    valid = evaluate_binance_usdm_empirical_block(
        candidate_id="candidate",
        source_id="source",
        intervals=_intervals(),
    )

    assert valid.prepared_sample is not None

    with pytest.raises(
        InvalidMetricInputError,
        match="must have a rejection reason",
    ):
        replace(
            rejected,
            rejection_reason=None,
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="must have rejection detail",
    ):
        replace(
            rejected,
            rejection_detail=None,
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="cannot contain a prepared sample",
    ):
        replace(
            rejected,
            prepared_sample=valid.prepared_sample,
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="zero canonical observations",
    ):
        replace(
            rejected,
            canonical_observation_count=1,
        )

    with pytest.raises(
        InvalidMetricInputError,
        match="cannot expose analysis timestamps",
    ):
        replace(
            rejected,
            analysis_start_timestamp_ns=1,
        )


def test_empty_interval_raw_bounds_are_empty_v3() -> None:
    import abmforge_finance.study.binance_usdm_blocks as blocks

    assert blocks._raw_bounds(()) == (
        None,
        None,
    )


def test_block_rejects_wrong_prepared_observation_count_v4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abmforge_finance.study.binance_usdm_blocks as blocks
    from abmforge_finance.study.stylized_empirical import (
        prepare_empirical_market_signature_sample,
    )

    wrong_sample = prepare_empirical_market_signature_sample(
        _intervals()[:-1],
        source_id="wrong-count",
    )

    monkeypatch.setattr(
        blocks,
        "prepare_empirical_market_signature_sample",
        lambda *args, **kwargs: wrong_sample,
    )

    result = blocks.evaluate_binance_usdm_empirical_block(
        candidate_id="candidate",
        source_id="source",
        intervals=_intervals(),
    )

    assert result.status is blocks.BinanceUsdMEmpiricalBlockStatus.REJECTED

    assert (
        result.rejection_reason
        is blocks.BinanceUsdMEmpiricalBlockRejectionReason.CANONICAL_PREPARATION_FAILURE
    )
