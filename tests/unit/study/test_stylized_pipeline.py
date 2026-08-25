"""Tests for the canonical Phase 11 market-signature pipeline."""

from __future__ import annotations

import pytest

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.stylized_estimators import (
    estimate_market_signatures,
)
from abmforge_finance.study.stylized_pipeline import (
    MarketSignatureInput,
    MarketSignatureInputProvenance,
    MarketSignatureSourceKind,
    PreparedMarketSignatureSample,
    estimate_prepared_market_signatures,
)


def _data() -> MarketSignatureInput:
    return MarketSignatureInput(
        log_returns=tuple(((index % 7) - 3) * 0.01 + index * 0.0001 for index in range(24)),
        aggressor_flow=tuple(1.0 if index % 2 == 0 else -1.0 for index in range(24)),
        pre_interval_thin_side_depth=tuple(float(index + 1) for index in range(24)),
        relative_thin_side_depth_drop=tuple(((index % 6) - 2) / 10.0 for index in range(24)),
    )


def _sample() -> PreparedMarketSignatureSample:
    data = _data()

    return PreparedMarketSignatureSample(
        data=data,
        provenance=MarketSignatureInputProvenance(
            source_kind=MarketSignatureSourceKind.SIMULATION,
            source_id="simulation-replicate-000",
            preparation_id="phase11-canonical-v1",
            observation_count=data.observation_count,
        ),
    )


def test_market_signature_input_is_immutable_and_aligned() -> None:
    data = _data()

    assert data.observation_count == 24
    assert isinstance(data.log_returns, tuple)
    assert isinstance(data.aggressor_flow, tuple)
    assert isinstance(
        data.pre_interval_thin_side_depth,
        tuple,
    )
    assert isinstance(
        data.relative_thin_side_depth_drop,
        tuple,
    )


def test_market_signature_input_normalizes_numeric_values_to_float() -> None:
    data = MarketSignatureInput(
        log_returns=(1, 2, 3),
        aggressor_flow=(-1, 0, 1),
        pre_interval_thin_side_depth=(3, 4, 5),
        relative_thin_side_depth_drop=(0, 1, -1),
    )

    assert data.log_returns == (1.0, 2.0, 3.0)
    assert data.aggressor_flow == (-1.0, 0.0, 1.0)


def test_market_signature_input_requires_tuple_series() -> None:
    with pytest.raises(
        TypeError,
        match="log_returns must be a tuple",
    ):
        MarketSignatureInput(
            log_returns=[1.0, 2.0],  # type: ignore[arg-type]
            aggressor_flow=(1.0, 2.0),
            pre_interval_thin_side_depth=(1.0, 2.0),
            relative_thin_side_depth_drop=(0.1, 0.2),
        )


def test_market_signature_input_rejects_unaligned_series() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="same length",
    ):
        MarketSignatureInput(
            log_returns=(1.0, 2.0, 3.0),
            aggressor_flow=(1.0, 2.0),
            pre_interval_thin_side_depth=(1.0, 2.0, 3.0),
            relative_thin_side_depth_drop=(0.1, 0.2, 0.3),
        )


def test_market_signature_input_rejects_non_finite_value() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="finite real number",
    ):
        MarketSignatureInput(
            log_returns=(1.0, float("nan")),
            aggressor_flow=(1.0, 2.0),
            pre_interval_thin_side_depth=(1.0, 2.0),
            relative_thin_side_depth_drop=(0.1, 0.2),
        )


def test_market_signature_input_rejects_negative_pre_depth() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="must be non-negative",
    ):
        MarketSignatureInput(
            log_returns=(1.0, 2.0),
            aggressor_flow=(1.0, 2.0),
            pre_interval_thin_side_depth=(1.0, -2.0),
            relative_thin_side_depth_drop=(0.1, 0.2),
        )


def test_provenance_requires_non_empty_identity() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="source_id",
    ):
        MarketSignatureInputProvenance(
            source_kind=MarketSignatureSourceKind.SIMULATION,
            source_id=" ",
            preparation_id="phase11-canonical-v1",
            observation_count=2,
        )


def test_prepared_sample_rejects_count_mismatch() -> None:
    data = _data()

    with pytest.raises(
        InvalidMetricInputError,
        match="observation_count",
    ):
        PreparedMarketSignatureSample(
            data=data,
            provenance=MarketSignatureInputProvenance(
                source_kind=MarketSignatureSourceKind.SIMULATION,
                source_id="simulation-replicate-000",
                preparation_id="phase11-canonical-v1",
                observation_count=23,
            ),
        )


def test_pipeline_uses_the_same_shared_estimator_implementation() -> None:
    sample = _sample()

    pipeline_result = estimate_prepared_market_signatures(sample)

    direct_result = estimate_market_signatures(
        log_returns=sample.data.log_returns,
        aggressor_flow=sample.data.aggressor_flow,
        pre_interval_thin_side_depth=(sample.data.pre_interval_thin_side_depth),
        relative_thin_side_depth_drop=(sample.data.relative_thin_side_depth_drop),
        maximum_lag=20,
        tail_threshold_sigma=3.0,
        low_depth_quantile=0.25,
        high_depth_quantile=0.75,
    )

    assert pipeline_result == direct_result


def test_pipeline_is_source_kind_agnostic_after_preparation() -> None:
    data = _data()

    simulation = PreparedMarketSignatureSample(
        data=data,
        provenance=MarketSignatureInputProvenance(
            source_kind=MarketSignatureSourceKind.SIMULATION,
            source_id="simulation",
            preparation_id="phase11-canonical-v1",
            observation_count=data.observation_count,
        ),
    )

    empirical = PreparedMarketSignatureSample(
        data=data,
        provenance=MarketSignatureInputProvenance(
            source_kind=MarketSignatureSourceKind.EMPIRICAL,
            source_id="empirical",
            preparation_id="phase11-canonical-v1",
            observation_count=data.observation_count,
        ),
    )

    assert estimate_prepared_market_signatures(simulation) == estimate_prepared_market_signatures(
        empirical
    )


def test_pipeline_rejects_insufficient_nonzero_flow_for_frozen_acf_lag() -> None:
    data = _data()

    sparse_flow = MarketSignatureInput(
        log_returns=data.log_returns,
        aggressor_flow=(
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            *data.aggressor_flow[5:],
        ),
        pre_interval_thin_side_depth=(data.pre_interval_thin_side_depth),
        relative_thin_side_depth_drop=(data.relative_thin_side_depth_drop),
    )

    sample = PreparedMarketSignatureSample(
        data=sparse_flow,
        provenance=MarketSignatureInputProvenance(
            source_kind=MarketSignatureSourceKind.SIMULATION,
            source_id="sparse-flow-simulation",
            preparation_id="phase11-canonical-v1",
            observation_count=sparse_flow.observation_count,
        ),
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="maximum_lag must be smaller",
    ):
        estimate_prepared_market_signatures(sample)


def test_market_signature_input_rejects_too_few_observations() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="at least two observations",
    ):
        MarketSignatureInput(
            log_returns=(1.0,),
            aggressor_flow=(1.0, 2.0),
            pre_interval_thin_side_depth=(1.0, 2.0),
            relative_thin_side_depth_drop=(0.1, 0.2),
        )


def test_market_signature_input_rejects_boolean_observation() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="finite real number",
    ):
        MarketSignatureInput(
            log_returns=(1.0, True),
            aggressor_flow=(1.0, 2.0),
            pre_interval_thin_side_depth=(1.0, 2.0),
            relative_thin_side_depth_drop=(0.1, 0.2),
        )


def test_provenance_rejects_invalid_source_kind() -> None:
    with pytest.raises(
        TypeError,
        match="MarketSignatureSourceKind",
    ):
        MarketSignatureInputProvenance(
            source_kind="simulation",  # type: ignore[arg-type]
            source_id="source",
            preparation_id="preparation",
            observation_count=2,
        )


def test_provenance_rejects_empty_preparation_id() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="preparation_id",
    ):
        MarketSignatureInputProvenance(
            source_kind=MarketSignatureSourceKind.SIMULATION,
            source_id="source",
            preparation_id=" ",
            observation_count=2,
        )


def test_provenance_rejects_invalid_observation_count() -> None:
    with pytest.raises(
        InvalidMetricInputError,
        match="positive integer",
    ):
        MarketSignatureInputProvenance(
            source_kind=MarketSignatureSourceKind.SIMULATION,
            source_id="source",
            preparation_id="preparation",
            observation_count=0,
        )


def test_prepared_sample_rejects_invalid_data_type() -> None:
    provenance = MarketSignatureInputProvenance(
        source_kind=MarketSignatureSourceKind.SIMULATION,
        source_id="source",
        preparation_id="preparation",
        observation_count=2,
    )

    with pytest.raises(
        TypeError,
        match="data must be a MarketSignatureInput",
    ):
        PreparedMarketSignatureSample(
            data=object(),  # type: ignore[arg-type]
            provenance=provenance,
        )


def test_prepared_sample_rejects_invalid_provenance_type() -> None:
    data = MarketSignatureInput(
        log_returns=(1.0, 2.0),
        aggressor_flow=(1.0, -1.0),
        pre_interval_thin_side_depth=(2.0, 3.0),
        relative_thin_side_depth_drop=(0.1, -0.1),
    )

    with pytest.raises(
        TypeError,
        match="MarketSignatureInputProvenance",
    ):
        PreparedMarketSignatureSample(
            data=data,
            provenance=object(),  # type: ignore[arg-type]
        )


def test_pipeline_rejects_invalid_sample_type() -> None:
    with pytest.raises(
        TypeError,
        match="PreparedMarketSignatureSample",
    ):
        estimate_prepared_market_signatures(
            object(),  # type: ignore[arg-type]
        )
