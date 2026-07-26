"""Domain model.

Everything is frozen and hashable so that clustering can use plain set algebra and
so results are reproducible between runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SignalKind(StrEnum):
    """What layer a signal comes from.

    Kept coarse on purpose: the useful triage question is "which layer is talking",
    not a taxonomy nobody remembers under pressure.
    """

    RESOURCE = "resource"
    SATURATION = "saturation"
    DATA_STORE = "data_store"
    NETWORK = "network"
    APPLICATION = "application"
    LIFECYCLE = "lifecycle"
    WORKLOAD = "workload"
    TOPOLOGY = "topology"


@dataclass(frozen=True, slots=True)
class Signal:
    """One observable fact extracted from a postmortem.

    `token` is the canonical name used for comparison across incidents.
    `evidence` keeps the original snippet so every conclusion stays auditable.
    """

    token: str
    kind: SignalKind
    evidence: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.token


@dataclass(frozen=True, slots=True)
class Incident:
    """A parsed postmortem."""

    id: str
    title: str
    source: str
    occurred_on: str | None = None
    severity: str | None = None
    service: str | None = None
    trigger: str | None = None
    mitigation: str | None = None
    root_cause_addressed: bool = False
    signals: tuple[Signal, ...] = field(default_factory=tuple)

    @property
    def tokens(self) -> frozenset[str]:
        return frozenset(s.token for s in self.signals)

    def evidence_for(self, token: str) -> str | None:
        return next((s.evidence for s in self.signals if s.token == token), None)


@dataclass(frozen=True, slots=True)
class Pattern:
    """A group of incidents that share a distinctive signal fingerprint."""

    id: str
    name: str
    incident_ids: tuple[str, ...]
    distinctive: tuple[str, ...]
    shared: frozenset[str]

    @property
    def size(self) -> int:
        return len(self.incident_ids)
