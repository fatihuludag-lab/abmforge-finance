"""Student-t two-sided p-value tests."""

from dataclasses import replace

import pytest

from abmforge_finance.calibration import (
    CalibrationScenario,
    PairedTreatmentContrast,
    paired_treatment_two_sided_p_value,
    student_t_two_sided_p_value,
)
from abmforge_finance.exceptions import CalibrationInferenceError


@pytest.mark.parametrize(
    ("df", "critical"),
    [
        (1, 12.7062047362),
        (2, 4.3026527297),
        (9, 2.2621571628),
        (29, 2.0452296421),
    ],
)
def test_student_t_two_sided_reference_at_five_percent(
    df: int,
    critical: float,
) -> None:
    assert student_t_two_sided_p_value(
        critical,
        df,
    ) == pytest.approx(0.05, rel=2e-9)


def test_student_t_two_sided_handles_zero_and_infinity() -> None:
    assert student_t_two_sided_p_value(0.0, 9) == pytest.approx(1.0)
    assert student_t_two_sided_p_value(float("inf"), 9) == 0.0
    assert student_t_two_sided_p_value(float("-inf"), 9) == 0.0


@pytest.mark.parametrize(
    ("statistic", "df"),
    [
        (float("nan"), 9),
        (1.0, 0),
        (1.0, True),
    ],
)
def test_student_t_two_sided_rejects_invalid_inputs(
    statistic: float,
    df: object,
) -> None:
    with pytest.raises(CalibrationInferenceError):
        student_t_two_sided_p_value(
            statistic,
            df,  # type: ignore[arg-type]
        )


def _contrast(
    *,
    mean_difference: float,
    standard_error: float,
) -> PairedTreatmentContrast:
    control = CalibrationScenario(
        "p",
        "control",
        2,
        (("x", "0"),),
    )
    treatment = CalibrationScenario(
        "p",
        "treatment",
        2,
        (("x", "1"),),
    )
    return PairedTreatmentContrast(
        metric_name="metric",
        control_scenario=control,
        treatment_scenario=treatment,
        changed_parameters=(("x", "0", "1"),),
        seeds=(1, 2, 3),
        differences=(mean_difference,) * 3,
        mean_difference=mean_difference,
        sample_std_difference=0.0,
        standard_error=standard_error,
        confidence_level=0.95,
        critical_value=4.3026527297,
        confidence_interval_lower=mean_difference,
        confidence_interval_upper=mean_difference,
    )


def test_paired_treatment_p_value_handles_degenerate_se() -> None:
    assert (
        paired_treatment_two_sided_p_value(
            _contrast(
                mean_difference=0.0,
                standard_error=0.0,
            )
        )
        == 1.0
    )
    assert (
        paired_treatment_two_sided_p_value(
            _contrast(
                mean_difference=2.0,
                standard_error=0.0,
            )
        )
        == 0.0
    )


def test_paired_p_value_rejects_wrong_type_and_negative_se() -> None:
    with pytest.raises(TypeError, match="PairedTreatmentContrast"):
        paired_treatment_two_sided_p_value(
            object(),  # type: ignore[arg-type]
        )

    contrast = _contrast(
        mean_difference=1.0,
        standard_error=0.5,
    )
    with pytest.raises(
        CalibrationInferenceError,
        match="standard_error",
    ):
        paired_treatment_two_sided_p_value(replace(contrast, standard_error=-0.5))
