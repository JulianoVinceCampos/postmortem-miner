"""Clustering behaviour, including the parts that must NOT happen."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from postmortem_miner import patterns
from postmortem_miner.models import Incident, Signal, SignalKind


def make(ident: str, tokens: list[str]) -> Incident:
    return Incident(
        id=ident,
        title=ident,
        source=f"{ident}.md",
        signals=tuple(
            Signal(token=token, kind=SignalKind.RESOURCE, evidence=token) for token in tokens
        ),
    )


def test_jaccard_bounds() -> None:
    assert patterns.jaccard(frozenset("ab"), frozenset("ab")) == 1.0
    assert patterns.jaccard(frozenset("ab"), frozenset("cd")) == 0.0
    assert patterns.jaccard(frozenset(), frozenset("ab")) == 0.0


@given(
    st.sets(st.text(min_size=1, max_size=3), max_size=6),
    st.sets(st.text(min_size=1, max_size=3), max_size=6),
)
def test_jaccard_is_symmetric_and_bounded(left: set[str], right: set[str]) -> None:
    value = patterns.jaccard(frozenset(left), frozenset(right))
    assert value == patterns.jaccard(frozenset(right), frozenset(left))
    assert 0.0 <= value <= 1.0


def test_identical_incidents_cluster_together() -> None:
    incidents = [make("a", ["x", "y", "z"]), make("b", ["x", "y", "z"])]
    found = patterns.find_patterns(incidents)
    assert len(found) == 1
    assert set(found[0].incident_ids) == {"a", "b"}


def test_disjoint_incidents_do_not_cluster() -> None:
    incidents = [make("a", ["x", "y"]), make("b", ["p", "q"])]
    assert patterns.find_patterns(incidents) == []


def test_singleton_is_an_anecdote_not_a_pattern() -> None:
    """One occurrence is never a pattern. It still counts against coverage."""
    incidents = [make("a", ["x", "y"]), make("b", ["x", "y"]), make("solo", ["k", "j"])]
    found = patterns.find_patterns(incidents)
    assert len(found) == 1
    assert patterns.coverage(incidents, found) == pytest.approx(2 / 3)


def test_distinctive_excludes_signals_common_to_everything() -> None:
    """A signal present in every incident cannot discriminate anything."""
    incidents = [
        make("a", ["noise", "x", "y"]),
        make("b", ["noise", "x", "y"]),
        make("c", ["noise", "p", "q"]),
        make("d", ["noise", "p", "q"]),
    ]
    found = patterns.find_patterns(incidents)
    assert len(found) == 2
    for pattern in found:
        assert "noise" not in pattern.distinctive


def test_shared_is_the_intersection() -> None:
    incidents = [make("a", ["x", "y", "extra"]), make("b", ["x", "y"])]
    pattern = patterns.find_patterns(incidents)[0]
    assert pattern.shared == frozenset({"x", "y"})


def test_patterns_are_ordered_by_size_desc() -> None:
    incidents = [
        make("a1", ["x", "y"]),
        make("a2", ["x", "y"]),
        make("a3", ["x", "y"]),
        make("b1", ["p", "q"]),
        make("b2", ["p", "q"]),
    ]
    found = patterns.find_patterns(incidents)
    assert [p.size for p in found] == [3, 2]
    assert found[0].id == "P1"


def test_threshold_controls_granularity() -> None:
    incidents = [make("a", ["x", "y", "z"]), make("b", ["x", "y", "w"])]
    assert len(patterns.find_patterns(incidents, threshold=0.4)) == 1
    assert patterns.find_patterns(incidents, threshold=0.9) == []


def test_empty_corpus_is_handled() -> None:
    assert patterns.find_patterns([]) == []
    assert patterns.coverage([], []) == 0.0


def test_matrix_shape_and_values() -> None:
    incidents = [make("a", ["x", "y"]), make("b", ["x", "y"])]
    found = patterns.find_patterns(incidents)
    columns, table = patterns.matrix(found, incidents)
    assert set(columns) == {"x", "y"}
    assert table["P1"]["x"] == 1.0
