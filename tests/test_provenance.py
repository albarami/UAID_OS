import pytest

from app.core.provenance import Fact, NoFreeFactsError, Source
from app.core.reasoning import muhasabah_gate


def test_fact_requires_source():
    with pytest.raises(NoFreeFactsError):
        Fact(claim="unsourced claim")


def test_gate_passes_with_sourced_fact():
    f = Fact(claim="x", sources=[Source(origin="doc")])
    result = muhasabah_gate("x", [f])
    assert result.passed
    assert result.failures == []
