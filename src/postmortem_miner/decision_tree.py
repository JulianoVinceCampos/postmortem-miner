"""Build a triage decision tree from labelled incidents.

Greedy information gain over binary signal presence. The tree answers exactly one
question, which is the only question that matters in the first two minutes of an
incident: *which known pattern is this?*

Depth is capped hard. A 9-level tree is mathematically better and operationally
useless, because nobody walks nine questions while production is down.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from postmortem_miner.models import Incident, Pattern

MAX_DEPTH = 4
_MIN_SAMPLES = 2
# Float comparison slack for information gain. Without it, two equally good splits
# would be picked by dict order and the tree would differ between runs.
_GAIN_EPS = 1e-12


@dataclass(slots=True)
class Node:
    """A tree node: either a question (`token` set) or a leaf (`label` set)."""

    token: str | None = None
    label: str | None = None
    support: int = 0
    yes: Node | None = None
    no: Node | None = None
    tie: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_leaf(self) -> bool:
        return self.token is None


def _entropy(labels: Sequence[str]) -> float:
    if not labels:
        return 0.0
    total = len(labels)
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _majority(labels: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    best = max(counts.values())
    winners = tuple(sorted(label for label, count in counts.items() if count == best))
    return winners[0], winners[1:]


def _best_split(
    samples: Sequence[tuple[frozenset[str], str]], candidates: Sequence[str]
) -> tuple[str | None, float]:
    base = _entropy([label for _, label in samples])
    best_token: str | None = None
    best_gain = 0.0
    total = len(samples)

    for token in candidates:
        yes = [label for tokens, label in samples if token in tokens]
        no = [label for tokens, label in samples if token not in tokens]
        if not yes or not no:
            continue
        gain = base - (len(yes) / total * _entropy(yes) + len(no) / total * _entropy(no))
        # Deterministic tie-break by token name keeps output stable across runs.
        tied = abs(gain - best_gain) <= _GAIN_EPS and best_token is not None
        if gain > best_gain + _GAIN_EPS or (tied and token < best_token):
            best_token, best_gain = token, gain
    return best_token, best_gain


def _grow(
    samples: Sequence[tuple[frozenset[str], str]],
    candidates: Sequence[str],
    depth: int,
) -> Node:
    labels = [label for _, label in samples]
    label, tie = _majority(labels)

    if depth >= MAX_DEPTH or len(samples) < _MIN_SAMPLES or _entropy(labels) == 0.0:
        return Node(label=label, support=len(samples), tie=tie)

    token, gain = _best_split(samples, candidates)
    if token is None or gain <= 0.0:
        return Node(label=label, support=len(samples), tie=tie)

    remaining = [c for c in candidates if c != token]
    return Node(
        token=token,
        support=len(samples),
        yes=_grow([s for s in samples if token in s[0]], remaining, depth + 1),
        no=_grow([s for s in samples if token not in s[0]], remaining, depth + 1),
    )


def build(incidents: Sequence[Incident], patterns: Sequence[Pattern]) -> Node:
    """Grow the triage tree. Incidents outside any pattern are labelled `unknown`."""
    label_of = {
        incident_id: f"{pattern.id} {pattern.name}"
        for pattern in patterns
        for incident_id in pattern.incident_ids
    }
    samples = [(i.tokens, label_of.get(i.id, "unknown")) for i in incidents]
    if not samples:
        return Node(label="unknown", support=0)

    candidates = sorted({token for pattern in patterns for token in pattern.distinctive})
    if not candidates:
        candidates = sorted({t for tokens, _ in samples for t in tokens})
    return _grow(samples, candidates, depth=0)


def to_mermaid(root: Node) -> str:
    """Render as a Mermaid flowchart, ready to paste into a README or runbook."""
    lines = ["flowchart TD"]
    counter = 0

    def walk(node: Node) -> str:
        nonlocal counter
        name = f"n{counter}"
        counter += 1
        if node.is_leaf:
            label = node.label or "unknown"
            lines.append(f'    {name}["{label}<br/>n={node.support}"]')
            return name
        lines.append(f'    {name}{{"{node.token}?"}}')
        if node.yes is not None:
            lines.append(f"    {name} -->|yes| {walk(node.yes)}")
        if node.no is not None:
            lines.append(f"    {name} -->|no| {walk(node.no)}")
        return name

    walk(root)
    return "\n".join(lines)


def depth(node: Node) -> int:
    if node.is_leaf:
        return 0
    children = [child for child in (node.yes, node.no) if child is not None]
    return 1 + max((depth(child) for child in children), default=0)


def classify_path(root: Node, tokens: frozenset[str]) -> tuple[str, tuple[tuple[str, bool], ...]]:
    """Walk the tree and return both the label and the questions asked on the way.

    The path is what makes the answer arguable. During an incident the label alone is a
    verdict; the label plus "because pool.exhausted was present and lock.contention was
    not" is something an engineer can push back on.
    """
    node = root
    path: list[tuple[str, bool]] = []
    while not node.is_leaf and node.token is not None:
        answer = node.token in tokens
        branch = node.yes if answer else node.no
        if branch is None:
            break
        path.append((node.token, answer))
        node = branch
    return node.label or "unknown", tuple(path)


def classify(root: Node, tokens: frozenset[str]) -> str:
    """Walk the tree for a live incident's signal set and return the pattern label."""
    return classify_path(root, tokens)[0]
