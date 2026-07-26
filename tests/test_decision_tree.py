"""The tree is the deliverable an on-call engineer actually uses."""

from __future__ import annotations

from postmortem_miner import decision_tree, patterns
from postmortem_miner.models import Incident, Signal, SignalKind


def make(ident: str, tokens: list[str]) -> Incident:
    return Incident(
        id=ident,
        title=ident,
        source=f"{ident}.md",
        signals=tuple(Signal(token=t, kind=SignalKind.APPLICATION, evidence=t) for t in tokens),
    )


def two_families() -> tuple[list[Incident], list]:
    incidents = [
        make("a1", ["pool", "lock"]),
        make("a2", ["pool", "lock"]),
        make("b1", ["heap", "gc"]),
        make("b2", ["heap", "gc"]),
    ]
    return incidents, patterns.find_patterns(incidents)


def test_builds_a_tree_that_separates_families() -> None:
    incidents, found = two_families()
    root = decision_tree.build(incidents, found)
    assert not root.is_leaf
    assert decision_tree.depth(root) >= 1


def test_classify_routes_each_family_to_its_own_pattern() -> None:
    incidents, found = two_families()
    root = decision_tree.build(incidents, found)
    left = decision_tree.classify(root, frozenset({"pool", "lock"}))
    right = decision_tree.classify(root, frozenset({"heap", "gc"}))
    assert left != right
    assert left.startswith("P")
    assert right.startswith("P")


def test_unknown_signals_do_not_crash_classification() -> None:
    incidents, found = two_families()
    root = decision_tree.build(incidents, found)
    assert decision_tree.classify(root, frozenset({"something-new"}))


def test_empty_input_returns_unknown_leaf() -> None:
    root = decision_tree.build([], [])
    assert root.is_leaf
    assert root.label == "unknown"
    assert decision_tree.depth(root) == 0


def test_pure_label_set_becomes_a_leaf() -> None:
    incidents = [make("a1", ["pool"]), make("a2", ["pool"])]
    found = patterns.find_patterns(incidents)
    root = decision_tree.build(incidents, found)
    assert root.is_leaf, "no question is needed when every incident has the same label"


def test_depth_is_capped() -> None:
    """Deeper trees score better and help nobody at 3am."""
    incidents = [make(f"i{n}", [f"s{n}", f"s{n + 1}", "common"]) for n in range(12)]
    found = patterns.find_patterns(incidents, threshold=0.3)
    root = decision_tree.build(incidents, found)
    assert decision_tree.depth(root) <= decision_tree.MAX_DEPTH


def test_tree_is_deterministic() -> None:
    incidents, found = two_families()
    first = decision_tree.to_mermaid(decision_tree.build(incidents, found))
    second = decision_tree.to_mermaid(decision_tree.build(incidents, found))
    assert first == second


def test_mermaid_output_is_renderable() -> None:
    incidents, found = two_families()
    mermaid = decision_tree.to_mermaid(decision_tree.build(incidents, found))
    assert mermaid.startswith("flowchart TD")
    assert "-->|yes|" in mermaid
    assert "-->|no|" in mermaid
    assert mermaid.count("n0") >= 1
