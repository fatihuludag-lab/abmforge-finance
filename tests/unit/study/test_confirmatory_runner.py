"""Official confirmatory runner boundary."""

from __future__ import annotations

from typing import cast

import pytest

from abmforge_finance.calibration import CalibrationExperimentResult
from abmforge_finance.study import confirmatory as confirmatory_module
from abmforge_finance.study import (
    flagship_narrative_stability_protocol,
)
from abmforge_finance.study.confirmatory import (
    ConfirmatoryArtifact,
    PrecisionPilotDecision,
)


def test_official_runner_verifies_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = flagship_narrative_stability_protocol()
    calls: list[str] = []

    monkeypatch.setattr(
        confirmatory_module,
        "flagship_narrative_stability_protocol",
        lambda: protocol,
    )
    monkeypatch.setattr(
        confirmatory_module,
        "verify_bundled_flagship_protocol",
        lambda value: calls.append(f"verify:{value.protocol_id}"),
    )

    decision = PrecisionPilotDecision(
        artifact_sha256="a" * 64,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_fingerprint=protocol.fingerprint,
        precision_source_git_commit="b" * 40,
        pilot_seed_namespace=protocol.pilot_seed_namespace,
        pilot_seed_count=160,
        pilot_seed_fingerprint="c" * 64,
        selected_seed_count=10,
    )

    def fake_loader(
        *args: object,
        **kwargs: object,
    ) -> PrecisionPilotDecision:
        calls.append("load")
        return decision

    monkeypatch.setattr(
        confirmatory_module,
        "load_precision_pilot_decision",
        fake_loader,
    )

    fake_experiments = cast(
        tuple[CalibrationExperimentResult, ...],
        tuple(object() for _ in protocol.homogeneities),
    )

    def fake_sweep(
        *args: object,
        **kwargs: object,
    ) -> tuple[CalibrationExperimentResult, ...]:
        calls.append("sweep")
        return fake_experiments

    monkeypatch.setattr(
        confirmatory_module,
        "run_narrative_stability_homogeneity_sweep",
        fake_sweep,
    )

    sentinel = cast(ConfirmatoryArtifact, object())

    def fake_builder(
        protocol_arg: object,
        decision_arg: object,
        experiments_arg: object,
        *,
        source_git_commit: str,
    ) -> ConfirmatoryArtifact:
        assert protocol_arg == protocol
        assert decision_arg is decision
        assert experiments_arg is fake_experiments
        assert source_git_commit == "d" * 40
        calls.append("build")
        return sentinel

    monkeypatch.setattr(
        confirmatory_module,
        "build_confirmatory_artifact",
        fake_builder,
    )

    result = confirmatory_module.run_flagship_confirmatory(
        precision_artifact_path="unused.json",
        source_git_commit="d" * 40,
    )

    assert result is sentinel
    assert calls == [
        f"verify:{protocol.protocol_id}",
        "load",
        "sweep",
        "build",
    ]
