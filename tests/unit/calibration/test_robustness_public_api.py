"""Public API tests for calibration robustness."""

from abmforge_finance import CalibrationRobustnessError
from abmforge_finance.calibration import (
    BaselineEcologyAudit,
    NormalizedSensitivity,
    RobustnessClassification,
    TreatmentFamilyAudit,
    audit_parameter_sweep,
    build_baseline_ecology_audit,
)


def test_calibration_robustness_public_api() -> None:
    assert issubclass(CalibrationRobustnessError, Exception)
    assert BaselineEcologyAudit.__name__ == "BaselineEcologyAudit"
    assert NormalizedSensitivity.__name__ == "NormalizedSensitivity"
    assert TreatmentFamilyAudit.__name__ == "TreatmentFamilyAudit"
    assert RobustnessClassification.ROBUST_POSITIVE.value == "ROBUST_POSITIVE"
    assert callable(audit_parameter_sweep)
    assert callable(build_baseline_ecology_audit)
