"""Public API tests for narrative homogeneity experiments."""

import abmforge_finance
from abmforge_finance import experiments


def test_narrative_homogeneity_api_is_exported() -> None:
    for name in (
        "NarrativeAgentAssignment",
        "NarrativeHomogeneityMeasurement",
        "NarrativeHomogeneityTreatment",
        "build_narrative_homogeneity_sweep",
        "measure_narrative_homogeneity",
    ):
        assert getattr(abmforge_finance, name) is getattr(experiments, name)

    assert issubclass(abmforge_finance.InvalidNarrativeTreatmentError, Exception)
