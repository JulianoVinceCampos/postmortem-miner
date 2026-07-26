"""Group incidents into recurring patterns by signal fingerprint.

Single-linkage agglomerative clustering over Jaccard similarity of signal sets,
implemented with union-find. Chosen over k-means/DBSCAN for one practical reason:
you do not know K in advance, and single-linkage lets a chain of related incidents
join without forcing a centroid that means nothing operationally.

The interesting output is not the cluster itself but the *distinctive* signals: the
ones that separate this pattern from every other incident in the corpus. That is what
becomes a triage question.
"""

from __future__ import annotations

from collections.abc import Sequence

from postmortem_miner.models import Incident, Pattern

DEFAULT_THRESHOLD = 0.45
_MAX_DISTINCTIVE = 4
_MIN_SUPPORT = 0.6
# A signal present in every incident of the corpus is background noise, not a
# fingerprint. Requiring a margin over the outside support is what makes the column
# "distinctive" instead of merely "frequent".
_MIN_MARGIN = 0.2
_EPS = 1e-9


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Similarity of two signal sets. 0.0 when either is empty."""
    if not left or not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            self._parent[root_right] = root_left


def _cluster_indices(incidents: Sequence[Incident], threshold: float) -> list[list[int]]:
    union_find = _UnionFind(len(incidents))
    for i in range(len(incidents)):
        for j in range(i + 1, len(incidents)):
            if jaccard(incidents[i].tokens, incidents[j].tokens) >= threshold:
                union_find.union(i, j)

    groups: dict[int, list[int]] = {}
    for index in range(len(incidents)):
        groups.setdefault(union_find.find(index), []).append(index)
    # Biggest first, then by first member for a stable tie-break.
    return sorted(groups.values(), key=lambda g: (-len(g), g[0]))


def _distinctive(
    members: Sequence[Incident], others: Sequence[Incident]
) -> tuple[tuple[str, ...], frozenset[str]]:
    """Signals that are frequent inside the cluster and rare outside it."""
    shared = frozenset.intersection(*[i.tokens for i in members]) if members else frozenset()

    scores: list[tuple[float, str]] = []
    for token in {t for i in members for t in i.tokens}:
        support_in = sum(token in i.tokens for i in members) / len(members)
        support_out = sum(token in i.tokens for i in others) / len(others) if others else 0.0
        if support_in < _MIN_SUPPORT or support_in - support_out < _MIN_MARGIN:
            continue
        lift = support_in / (support_out + _EPS)
        scores.append((support_in - support_out + min(lift, 10.0) / 100, token))

    scores.sort(key=lambda pair: (-pair[0], pair[1]))
    return tuple(token for _, token in scores[:_MAX_DISTINCTIVE]), shared


def _humanize(tokens: Sequence[str]) -> str:
    """`saturation.pool.exhausted` -> `pool exhausted`, joined into a short label."""
    parts = [token.split(".", 1)[-1].replace(".", " ").replace("_", " ") for token in tokens[:2]]
    return " + ".join(parts) if parts else "unclassified"


def find_patterns(
    incidents: Sequence[Incident],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    min_size: int = 2,
) -> list[Pattern]:
    """Cluster incidents and describe each cluster by its distinctive signals.

    Clusters smaller than `min_size` are dropped: a single incident is not a pattern,
    it is an anecdote. They still count in the denominator of `coverage`.
    """
    if not incidents:
        return []

    patterns: list[Pattern] = []
    for position, group in enumerate(_cluster_indices(incidents, threshold), start=1):
        if len(group) < min_size:
            continue
        members = [incidents[i] for i in group]
        member_ids = {i.id for i in members}
        others = [i for i in incidents if i.id not in member_ids]
        distinctive, shared = _distinctive(members, others)
        patterns.append(
            Pattern(
                id=f"P{position}",
                name=_humanize(distinctive or tuple(sorted(shared))),
                incident_ids=tuple(i.id for i in members),
                distinctive=distinctive,
                shared=shared,
            )
        )
    return patterns


def coverage(incidents: Sequence[Incident], patterns: Sequence[Pattern]) -> float:
    """Fraction of incidents explained by at least one pattern (0.0-1.0)."""
    if not incidents:
        return 0.0
    covered = {incident_id for pattern in patterns for incident_id in pattern.incident_ids}
    return len(covered) / len(incidents)


def matrix(
    patterns: Sequence[Pattern], incidents: Sequence[Incident]
) -> tuple[tuple[str, ...], dict[str, dict[str, float]]]:
    """Pattern x signal support matrix, restricted to distinctive signals.

    Returns the ordered column list and, per pattern id, the support of each column.
    """
    columns: list[str] = []
    for pattern in patterns:
        for token in pattern.distinctive:
            if token not in columns:
                columns.append(token)

    by_id = {incident.id: incident for incident in incidents}
    table: dict[str, dict[str, float]] = {}
    for pattern in patterns:
        members = [by_id[i] for i in pattern.incident_ids if i in by_id]
        table[pattern.id] = {
            token: (sum(token in m.tokens for m in members) / len(members) if members else 0.0)
            for token in columns
        }
    return tuple(columns), table
