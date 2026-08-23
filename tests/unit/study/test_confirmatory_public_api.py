"""Public API checks for Phase 10F."""

from abmforge_finance import calibration, study


def test_confirmatory_public_api_is_exported() -> None:
    for name in (
        "paired_treatment_two_sided_p_value",
        "student_t_two_sided_p_value",
    ):
        assert hasattr(calibration, name)

    for name in (
        "ConfirmatoryArtifact",
        "ConfirmatoryContrastResult",
        "ConfirmatoryOutcomeResult",
        "HolmHypothesisResult",
        "OFFICIAL_FLAGSHIP_PRECISION_ARTIFACT_SHA256",
        "PrecisionPilotDecision",
        "build_confirmatory_artifact",
        "holm_adjust",
        "load_precision_pilot_decision",
        "run_flagship_confirmatory",
        "verify_confirmatory_artifact",
        "verify_confirmatory_experiments",
        "write_confirmatory_artifact",
    ):
        assert hasattr(study, name)
