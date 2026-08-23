"""Holm multiplicity tests."""

import pytest

from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study.confirmatory import holm_adjust


def test_holm_reference_example_preserves_input_order() -> None:
    results = holm_adjust(
        (
            ("h1", 0.01),
            ("h2", 0.04),
            ("h3", 0.03),
            ("h4", 0.20),
        ),
        familywise_alpha=0.05,
    )

    assert tuple(item.hypothesis_id for item in results) == (
        "h1",
        "h2",
        "h3",
        "h4",
    )
    assert tuple(item.adjusted_p_value for item in results) == pytest.approx(
        (0.04, 0.09, 0.09, 0.20)
    )
    assert tuple(item.reject for item in results) == (
        True,
        False,
        False,
        False,
    )


def test_holm_ties_are_deterministic() -> None:
    results = holm_adjust(
        (
            ("b", 0.01),
            ("a", 0.01),
            ("c", 0.40),
        ),
        familywise_alpha=0.05,
    )
    by_id = {item.hypothesis_id: item for item in results}

    assert by_id["a"].adjusted_p_value == pytest.approx(0.03)
    assert by_id["b"].adjusted_p_value == pytest.approx(0.03)
    assert by_id["c"].adjusted_p_value == pytest.approx(0.40)
    assert by_id["a"].reject
    assert by_id["b"].reject
    assert not by_id["c"].reject


@pytest.mark.parametrize(
    "hypotheses",
    [
        (),
        (("", 0.1),),
        (("x", -0.1),),
        (("x", 1.1),),
        (("x", float("nan")),),
        (("x", 0.1), ("x", 0.2)),
    ],
)
def test_holm_rejects_invalid_families(
    hypotheses: tuple[tuple[str, float], ...],
) -> None:
    with pytest.raises(StudyProtocolError):
        holm_adjust(
            hypotheses,
            familywise_alpha=0.05,
        )


@pytest.mark.parametrize(
    "alpha",
    [0.0, 1.0, float("nan"), True],
)
def test_holm_rejects_invalid_alpha(alpha: object) -> None:
    with pytest.raises(StudyProtocolError):
        holm_adjust(
            (("h", 0.1),),
            familywise_alpha=alpha,  # type: ignore[arg-type]
        )
