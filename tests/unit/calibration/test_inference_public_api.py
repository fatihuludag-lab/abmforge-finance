"""Public API tests for calibration inference."""

from abmforge_finance.calibration import (
    ContrastRegionSummary,
    PairedTreatmentContrast,
    paired_treatment_contrast,
    student_t_critical_value,
    summarize_contrast_region,
)


def test_calibration_inference_public_api() -> None:
    assert PairedTreatmentContrast.__name__ == "PairedTreatmentContrast"
    assert ContrastRegionSummary.__name__ == "ContrastRegionSummary"
    assert callable(paired_treatment_contrast)
    assert callable(student_t_critical_value)
    assert callable(summarize_contrast_region)
