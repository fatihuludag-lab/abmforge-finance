"""Public study API tests."""

from abmforge_finance import study


def test_study_api_is_public() -> None:
    for name in (
        "FlagshipStudyProtocol",
        "MultiplicityMethod",
        "OutcomeRole",
        "PrecisionPilotPlan",
        "PrecisionPilotReport",
        "PrecisionTarget",
        "RobustnessRegime",
        "StudyOutcome",
        "apply_robustness_regime",
        "bundled_flagship_protocol_mapping",
        "confirmatory_seed_tuple",
        "evaluate_precision_pilot",
        "flagship_narrative_stability_protocol",
        "precision_pilot_seed_tuple",
        "study_seed_tuple",
    ):
        assert hasattr(study, name)
