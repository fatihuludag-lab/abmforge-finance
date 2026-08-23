"""Seed isolation tests for pilot and confirmatory study stages."""

import pytest

from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    confirmatory_seed_tuple,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
    study_seed_tuple,
)


def test_pilot_and_confirmatory_seed_namespaces_are_disjoint() -> None:
    protocol = flagship_narrative_stability_protocol()
    pilot = precision_pilot_seed_tuple(protocol)
    confirmatory = confirmatory_seed_tuple(protocol, 40)

    assert len(pilot) == 160
    assert len(set(pilot)) == 160
    assert len(confirmatory) == 40
    assert set(pilot).isdisjoint(confirmatory)


def test_seed_derivation_is_deterministic_and_namespace_sensitive() -> None:
    protocol = flagship_narrative_stability_protocol()

    assert study_seed_tuple(protocol, namespace="x", count=4) == study_seed_tuple(
        protocol,
        namespace="x",
        count=4,
    )
    assert study_seed_tuple(protocol, namespace="x", count=4) != study_seed_tuple(
        protocol,
        namespace="y",
        count=4,
    )


def test_confirmatory_count_must_be_prespecified() -> None:
    protocol = flagship_narrative_stability_protocol()

    with pytest.raises(StudyProtocolError, match="prespecified candidate"):
        confirmatory_seed_tuple(protocol, 30)
