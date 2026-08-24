"""Validation-path tests for the Phase 11A contract."""

from dataclasses import replace
from decimal import Decimal
from typing import cast

import pytest

from abmforge_finance.domain import NarrativeDirection
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    StylizedFactExpectation,
    StylizedFactRole,
    StylizedFactSpec,
    StylizedValidationProtocol,
    build_stylized_validation_benchmark_config,
    stylized_fact_validation_protocol,
    stylized_validation_seed_tuple,
    verify_bundled_stylized_validation_protocol,
)


def test_stylized_fact_spec_rejects_invalid_identity_and_types() -> None:
    base = stylized_fact_validation_protocol().facts[0]

    with pytest.raises(StudyProtocolError, match="SF-XX"):
        replace(base, fact_id="bad")
    with pytest.raises(StudyProtocolError, match="name"):
        replace(base, name="")
    with pytest.raises(StudyProtocolError, match="StylizedFactRole"):
        replace(base, role="primary")  # type: ignore[arg-type]
    with pytest.raises(StudyProtocolError, match="estimator_id"):
        replace(base, estimator_id="")
    with pytest.raises(StudyProtocolError, match="StylizedFactExpectation"):
        replace(base, expected_relation="bad")  # type: ignore[arg-type]


def test_stylized_fact_spec_rejects_invalid_parameters() -> None:
    base = stylized_fact_validation_protocol().facts[0]

    with pytest.raises(StudyProtocolError, match="non-empty tuple"):
        replace(base, parameters=())
    with pytest.raises(StudyProtocolError, match="key/value pairs"):
        replace(base, parameters=(("only-one",),))  # type: ignore[arg-type]
    with pytest.raises(StudyProtocolError, match="parameter key"):
        replace(base, parameters=(("", "value"),))
    with pytest.raises(StudyProtocolError, match="parameter value"):
        replace(base, parameters=(("key", ""),))
    with pytest.raises(StudyProtocolError, match="unique"):
        replace(
            base,
            parameters=(("key", "1"), ("key", "2")),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_id": ""},
        {"protocol_version": ""},
        {"protocol_status": ""},
        {"purpose": ""},
        {"source_benchmark_family": ""},
        {"seed_namespace": ""},
    ],
)
def test_protocol_rejects_empty_strings(changes: dict[str, object]) -> None:
    with pytest.raises(StudyProtocolError, match="non-empty"):
        replace(
            stylized_fact_validation_protocol(),
            **changes,  # type: ignore[arg-type]
        )


def test_protocol_rejects_invalid_source_fingerprint() -> None:
    with pytest.raises(StudyProtocolError, match="lowercase SHA-256"):
        replace(
            stylized_fact_validation_protocol(),
            source_flagship_protocol_fingerprint="BAD",
        )


@pytest.mark.parametrize(
    "value",
    [
        Decimal("-0.1"),
        Decimal("1.1"),
        Decimal("NaN"),
    ],
)
def test_protocol_rejects_invalid_homogeneity(value: Decimal) -> None:
    with pytest.raises(StudyProtocolError, match="validation_homogeneity"):
        replace(
            stylized_fact_validation_protocol(),
            validation_homogeneity=value,
        )


def test_protocol_rejects_invalid_direction_cycle() -> None:
    protocol = stylized_fact_validation_protocol()

    with pytest.raises(StudyProtocolError, match="at least two"):
        replace(protocol, direction_cycle=(NarrativeDirection.BULLISH,))
    with pytest.raises(StudyProtocolError, match="bullish or bearish"):
        replace(
            protocol,
            direction_cycle=(
                NarrativeDirection.BULLISH,
                NarrativeDirection.NEUTRAL,
            ),
        )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("burn_in_periods", 0, "positive integer"),
        ("analysis_horizon", 0, "positive integer"),
        ("replicate_count", 0, "positive integer"),
        ("maximum_acf_lag", 0, "positive integer"),
        ("maximum_acf_lag", 4096, "smaller"),
    ],
)
def test_protocol_rejects_invalid_integer_design(
    field: str,
    value: int,
    match: str,
) -> None:
    with pytest.raises(StudyProtocolError, match=match):
        replace(
            stylized_fact_validation_protocol(),
            **{field: value},  # type: ignore[arg-type]
        )


def test_protocol_rejects_price_return_and_quantile_drift() -> None:
    protocol = stylized_fact_validation_protocol()

    with pytest.raises(StudyProtocolError, match="price_basis"):
        replace(protocol, price_basis="last")
    with pytest.raises(StudyProtocolError, match="return_type"):
        replace(protocol, return_type="simple")
    with pytest.raises(StudyProtocolError, match="quantiles"):
        replace(
            protocol,
            empirical_reference_lower_quantile=Decimal("0.95"),
            empirical_reference_upper_quantile=Decimal("0.05"),
        )


def test_protocol_rejects_inference_calibration_and_estimator_drift() -> None:
    protocol = stylized_fact_validation_protocol()

    with pytest.raises(StudyProtocolError, match="inference_scope"):
        replace(protocol, inference_scope="significance-search")
    with pytest.raises(StudyProtocolError, match="estimator_lock"):
        replace(protocol, estimator_lock="different-estimators")
    with pytest.raises(StudyProtocolError, match="must not permit"):
        replace(protocol, model_calibration_permitted=True)


def test_protocol_rejects_fact_collection_drift() -> None:
    protocol = stylized_fact_validation_protocol()
    first = protocol.facts[0]

    with pytest.raises(StudyProtocolError, match="non-empty tuple"):
        replace(protocol, facts=())
    with pytest.raises(StudyProtocolError, match="StylizedFactSpec"):
        replace(protocol, facts=(object(),))  # type: ignore[arg-type]
    with pytest.raises(StudyProtocolError, match="IDs must be unique"):
        replace(protocol, facts=(first, first))

    duplicate_name = replace(
        protocol.facts[1],
        fact_id="SF-99",
        name=first.name,
    )
    with pytest.raises(StudyProtocolError, match="names must be unique"):
        replace(protocol, facts=(first, duplicate_name))

    duplicate_estimator = replace(
        protocol.facts[1],
        fact_id="SF-99",
        name="different-name",
        estimator_id=first.estimator_id,
    )
    with pytest.raises(StudyProtocolError, match="estimator IDs must be unique"):
        replace(protocol, facts=(first, duplicate_estimator))


def test_protocol_requires_primary_fact_and_matching_maximum_lag() -> None:
    protocol = stylized_fact_validation_protocol()
    diagnostics = tuple(replace(fact, role=StylizedFactRole.DIAGNOSTIC) for fact in protocol.facts)
    with pytest.raises(StudyProtocolError, match="at least one primary"):
        replace(protocol, facts=diagnostics)

    first = protocol.facts[0]
    mismatched = replace(
        first,
        parameters=(
            ("maximum_lag", "99"),
            ("series", "log-mid-return"),
            ("summary", "lag-vector-and-mean-absolute-acf"),
        ),
    )
    with pytest.raises(StudyProtocolError, match="must match protocol"):
        replace(protocol, facts=(mismatched, *protocol.facts[1:]))


def test_public_helpers_reject_wrong_protocol_types() -> None:
    invalid = object()

    with pytest.raises(TypeError, match="StylizedValidationProtocol"):
        verify_bundled_stylized_validation_protocol(cast(StylizedValidationProtocol, invalid))
    with pytest.raises(TypeError, match="StylizedValidationProtocol"):
        stylized_validation_seed_tuple(cast(StylizedValidationProtocol, invalid))
    with pytest.raises(TypeError, match="StylizedValidationProtocol"):
        build_stylized_validation_benchmark_config(cast(StylizedValidationProtocol, invalid))


def test_custom_fact_type_validation_remains_strict() -> None:
    with pytest.raises(StudyProtocolError, match="StylizedFactRole"):
        StylizedFactSpec(
            fact_id="SF-99",
            name="custom",
            role="primary",  # type: ignore[arg-type]
            estimator_id="custom-estimator",
            expected_relation=(StylizedFactExpectation.POSITIVE_AGGRESSOR_FLOW_PRICE_IMPACT),
            parameters=(("key", "value"),),
        )


def test_protocol_class_rejects_boolean_integer_fields() -> None:
    protocol = stylized_fact_validation_protocol()

    with pytest.raises(StudyProtocolError, match="positive integer"):
        replace(protocol, replicate_count=True)


def test_protocol_type_is_public() -> None:
    protocol = stylized_fact_validation_protocol()
    assert isinstance(protocol, StylizedValidationProtocol)
