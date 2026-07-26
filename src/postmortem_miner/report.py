"""Render the analysis as markdown a human will actually read.

Order is deliberate: the number first, then the tree you can act on, then the evidence
that backs it. Same shape as a good postmortem.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from postmortem_miner import decision_tree
from postmortem_miner import patterns as patterns_mod
from postmortem_miner.decision_tree import Node
from postmortem_miner.models import Incident, Pattern


@dataclass(frozen=True, slots=True)
class Analysis:
    incidents: tuple[Incident, ...]
    patterns: tuple[Pattern, ...]
    tree: Node
    coverage: float
    elapsed_ms: float

    @property
    def unexplained(self) -> tuple[Incident, ...]:
        covered = {i for p in self.patterns for i in p.incident_ids}
        return tuple(i for i in self.incidents if i.id not in covered)


# Rounding guard: 5/5 can come back as 0.999... depending on the division order.
_FULL_SUPPORT = 0.99


def _support_cell(value: float) -> str:
    if value >= _FULL_SUPPORT:
        return "**100%**"
    return f"{value * 100:.0f}%" if value else "-"


def to_markdown(analysis: Analysis) -> str:
    out: list[str] = []
    add = out.append

    add("# Incident pattern analysis\n")
    add(
        f"**{len(analysis.patterns)} patterns explain "
        f"{analysis.coverage * 100:.0f}% of {len(analysis.incidents)} incidents** "
        f"(analysed in {analysis.elapsed_ms:.0f} ms, "
        f"triage depth {decision_tree.depth(analysis.tree)}).\n"
    )

    add("## Triage decision tree\n")
    add("Walk this top-down against a live incident's signals.\n")
    add("```mermaid")
    add(decision_tree.to_mermaid(analysis.tree))
    add("```\n")

    columns, table = patterns_mod.matrix(analysis.patterns, analysis.incidents)
    if columns:
        # Transposed on purpose: signals as rows. With 8+ patterns the natural
        # orientation produces a 20-column table that no one can read in markdown.
        add("## Signal x pattern matrix\n")
        add("Support of each distinctive signal within each pattern.\n")
        header = " | ".join(["signal", *[p.id for p in analysis.patterns]])
        add(f"| {header} |")
        add("|" + "---|" * (len(analysis.patterns) + 1))
        for token in columns:
            cells = [_support_cell(table[p.id][token]) for p in analysis.patterns]
            add(f"| `{token}` | " + " | ".join(cells) + " |")
        add("")
        legend = ", ".join(f"`{p.id}` {p.name}" for p in analysis.patterns)
        add(f"Legend: {legend}\n")

    add("## Patterns in detail\n")
    by_id = {incident.id: incident for incident in analysis.incidents}
    for pattern in analysis.patterns:
        add(f"### `{pattern.id}` {pattern.name}\n")
        add(
            f"- **incidents ({pattern.size}):** "
            + ", ".join(f"`{i}`" for i in pattern.incident_ids)
        )
        add(
            "- **distinctive signals:** "
            + (", ".join(f"`{t}`" for t in pattern.distinctive) or "-")
        )
        add("- **always present:** " + (", ".join(f"`{t}`" for t in sorted(pattern.shared)) or "-"))
        first = by_id.get(pattern.incident_ids[0]) if pattern.incident_ids else None
        if first and pattern.distinctive:
            evidence = first.evidence_for(pattern.distinctive[0])
            if evidence:
                add(f"- **sample evidence** (`{first.id}`): {evidence}")
        unaddressed = [
            i for i in pattern.incident_ids if i in by_id and not by_id[i].root_cause_addressed
        ]
        if unaddressed:
            add(
                f"- **root cause still open in {len(unaddressed)}/{pattern.size} occurrences** "
                "- recurrence is expected until that changes."
            )
        add("")

    if analysis.unexplained:
        add("## Not explained by any pattern\n")
        add("One incident is an anecdote, not a pattern. These are candidates to watch:\n")
        for incident in analysis.unexplained:
            tokens = ", ".join(f"`{t}`" for t in sorted(incident.tokens)[:5]) or "-"
            add(f"- `{incident.id}` - {incident.title} ({tokens})")
        add("")

    return "\n".join(out)


def to_json(analysis: Analysis) -> str:
    payload = {
        "incidents": len(analysis.incidents),
        "patterns": [
            {
                "id": pattern.id,
                "name": pattern.name,
                "size": pattern.size,
                "incident_ids": list(pattern.incident_ids),
                "distinctive": list(pattern.distinctive),
                "shared": sorted(pattern.shared),
            }
            for pattern in analysis.patterns
        ],
        "coverage": round(analysis.coverage, 4),
        "triage_depth": decision_tree.depth(analysis.tree),
        "elapsed_ms": round(analysis.elapsed_ms, 2),
        "unexplained": [incident.id for incident in analysis.unexplained],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def analyse(
    incidents: Sequence[Incident], *, threshold: float, elapsed_ms: float = 0.0
) -> Analysis:
    found = patterns_mod.find_patterns(incidents, threshold=threshold)
    return Analysis(
        incidents=tuple(incidents),
        patterns=tuple(found),
        tree=decision_tree.build(incidents, found),
        coverage=patterns_mod.coverage(incidents, found),
        elapsed_ms=elapsed_ms,
    )
