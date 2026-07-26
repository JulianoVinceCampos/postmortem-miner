"""The parser has one job: never be the reason a postmortem is skipped."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from postmortem_miner import parser


def test_reads_frontmatter(pool_lock_text: str) -> None:
    incident = parser.parse_text(pool_lock_text, source="pool.md")
    assert incident.id == "sample-01"
    assert incident.severity == "P1"
    assert incident.service == "svc-ledger"
    assert incident.occurred_on == "2026-03-14"


def test_falls_back_to_heading_and_filename(heap_text: str) -> None:
    incident = parser.parse_text(heap_text, source="/tmp/postmortem-heap-01.md")
    assert incident.id == "postmortem-heap-01"
    assert incident.title == "Heap exhaustion on one node"


def test_accepts_portuguese_field_aliases() -> None:
    text = "---\nseveridade: P2\nservico: svc-billing\n---\n\n# t\n\nPool em 80/80.\n"
    incident = parser.parse_text(text)
    assert incident.severity == "P2"
    assert incident.service == "svc-billing"


def test_parses_inline_and_block_lists() -> None:
    text = "---\ntags: [a, b]\nowners:\n  - alice\n  - bob\n---\n\n# t\n\nPool em 80/80.\n"
    incident = parser.parse_text(text)
    assert incident.signals  # body still parsed
    assert incident.title == "t"


def test_date_from_filename() -> None:
    incident = parser.parse_text("# t\n\nPool em 80/80.\n", source="postmortem-2026-05-09.md")
    assert incident.occurred_on == "2026-05-09"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Incidente iniciado em 2026-05-09 as 14h.", "2026-05-09"),
        ("Incidente iniciado em 09/05/2026 as 14h.", "2026-05-09"),
    ],
)
def test_date_from_body_in_both_orders(body: str, expected: str) -> None:
    """Brazilian postmortems write dd/mm/yyyy; tooling writes ISO. Accept both."""
    incident = parser.parse_text(f"# t\n\n{body}\n\nPool em 80/80.\n", source="x.md")
    assert incident.occurred_on == expected


def test_root_cause_addressed_flag(heap_text: str, pool_lock_text: str) -> None:
    assert parser.parse_text(heap_text).root_cause_addressed is True
    assert parser.parse_text(pool_lock_text).root_cause_addressed is False


def test_not_addressed_wins_over_addressed() -> None:
    """A postmortem that says both things is saying the root cause is still open."""
    text = "# t\n\nPool em 80/80.\n\n## Root cause\n\nCausa raiz nao tratada. Causa raiz tratada.\n"
    assert parser.parse_text(text).root_cause_addressed is False


def test_extracts_mitigation_section(pool_lock_text: str) -> None:
    incident = parser.parse_text(pool_lock_text)
    assert incident.mitigation is not None
    assert "Restart" in incident.mitigation


def test_parse_corpus_skips_files_without_signals(corpus_dir) -> None:
    (corpus_dir / "empty.md").write_text("# nothing to see here\n", encoding="utf-8")
    incidents = parser.parse_corpus(corpus_dir)
    assert len(incidents) == 4
    assert all(incident.signals for incident in incidents)


def test_parse_corpus_is_sorted(corpus_dir) -> None:
    ids = [incident.id for incident in parser.parse_corpus(corpus_dir)]
    assert ids == sorted(ids) or len(set(ids)) < len(ids)


def test_parse_corpus_rejects_missing_directory(tmp_path) -> None:
    with pytest.raises(NotADirectoryError):
        parser.parse_corpus(tmp_path / "nope")


def test_parse_file(corpus_dir) -> None:
    incident = parser.parse_file(corpus_dir / "pool-0.md")
    assert incident.tokens
    assert incident.evidence_for("saturation.pool.exhausted")
    assert incident.evidence_for("does.not.exist") is None


@settings(max_examples=120, deadline=None)
@given(st.text(max_size=300))
def test_parse_text_never_raises(text: str) -> None:
    incident = parser.parse_text(text, source="fuzz.md")
    assert incident.id
    assert isinstance(incident.tokens, frozenset)
