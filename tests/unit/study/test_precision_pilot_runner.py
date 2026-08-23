"""Official precision-pilot runner boundary without executing 800 real replicates."""

from __future__ import annotations

from typing import cast

import pytest

from abmforge_finance.calibration import CalibrationExperimentResult
from abmforge_finance.study import flagship_narrative_stability_protocol
from abmforge_finance.study import precision as precision_module
from abmforge_finance.study.precision import PrecisionPilotArtifact


def test_official_runner_verifies_protocol_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = flagship_narrative_stability_protocol()
    calls: list[str] = []

    monkeypatch.setattr(
        precision_module,
        "verify_bundled_flagship_protocol",
        lambda value: calls.append(f"verify:{value.protocol_id}"),
    )

    fake_experiments = cast(
        tuple[CalibrationExperimentResult, ...],
        tuple(object() for _ in protocol.homogeneities),
    )

    def fake_sweep(*args: object, **kwargs: object) -> tuple[CalibrationExperimentResult, ...]:
        calls.append("sweep")
        return fake_experiments

    monkeypatch.setattr(
        precision_module,
        "run_narrative_stability_homogeneity_sweep",
        fake_sweep,
    )

    sentinel = cast(PrecisionPilotArtifact, object())

    def fake_builder(
        protocol_arg: object,
        experiments_arg: object,
        *,
        source_git_commit: str,
    ) -> PrecisionPilotArtifact:
        assert protocol_arg == protocol
        assert experiments_arg is fake_experiments
        assert source_git_commit == "a" * 40
        calls.append("build")
        return sentinel

    monkeypatch.setattr(
        precision_module,
        "build_precision_pilot_artifact",
        fake_builder,
    )

    result = precision_module.run_flagship_precision_pilot(
        source_git_commit="a" * 40,
    )

    assert result is sentinel
    assert calls == [
        f"verify:{protocol.protocol_id}",
        "sweep",
        "build",
    ]
