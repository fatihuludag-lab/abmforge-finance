"""Validation tests for narrative-homogeneity measurement API."""

from decimal import Decimal

import pytest

from abmforge_finance import NarrativeDirection
from abmforge_finance.experiments import (
    NarrativeHomogeneityTreatment,
    measure_narrative_homogeneity,
)


def _treatment() -> NarrativeHomogeneityTreatment:
    return NarrativeHomogeneityTreatment(
        "H=0",
        ("a", "b"),
        Decimal("0"),
        NarrativeDirection.BULLISH,
    )


def test_measurement_rejects_wrong_dataset_type() -> None:
    with pytest.raises(TypeError, match="FinanceResearchDataset"):
        measure_narrative_homogeneity(
            object(),  # type: ignore[arg-type]
            _treatment(),
        )


def test_measurement_rejects_wrong_treatment_type() -> None:
    from abmforge_finance.recording import FinanceResearchDataset

    with pytest.raises(TypeError, match="NarrativeHomogeneityTreatment"):
        measure_narrative_homogeneity(
            FinanceResearchDataset(),
            object(),  # type: ignore[arg-type]
        )
