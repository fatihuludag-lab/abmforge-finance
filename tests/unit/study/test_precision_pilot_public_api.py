"""Public API tests for precision-pilot execution."""

from abmforge_finance import study


def test_precision_execution_api_is_exported() -> None:
    for name in (
        "PrecisionCheckpointArtifact",
        "PrecisionContrastWidth",
        "PrecisionMetricArtifact",
        "PrecisionPilotArtifact",
        "build_precision_pilot_artifact",
        "run_flagship_precision_pilot",
        "verify_bundled_flagship_protocol",
        "verify_precision_pilot_artifact",
        "verify_precision_pilot_experiments",
        "write_precision_pilot_artifact",
    ):
        assert hasattr(study, name)
