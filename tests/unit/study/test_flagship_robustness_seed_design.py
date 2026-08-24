import pytest

from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    confirmatory_seed_tuple,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)
from abmforge_finance.study.robustness import robustness_seed_tuple


def test_robustness_seeds_are_fresh_and_deterministic() -> None:
    protocol = flagship_narrative_stability_protocol()
    seeds = robustness_seed_tuple(protocol, 10)
    assert seeds == robustness_seed_tuple(protocol, 10)
    assert len(seeds) == len(set(seeds)) == 10
    assert not set(seeds).intersection(precision_pilot_seed_tuple(protocol))
    assert not set(seeds).intersection(confirmatory_seed_tuple(protocol, 10))


def test_robustness_seed_count_must_be_prespecified() -> None:
    with pytest.raises(StudyProtocolError, match="prespecified"):
        robustness_seed_tuple(flagship_narrative_stability_protocol(), 11)
