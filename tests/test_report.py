"""Report rendering: the part a reader judges the tool by."""

from __future__ import annotations

import json

from postmortem_miner import report
from postmortem_miner.parser import parse_corpus


def analysis_from(corpus_dir):
    return report.analyse(parse_corpus(corpus_dir), threshold=0.45, elapsed_ms=12.3)


def test_markdown_leads_with_the_number(corpus_dir) -> None:
    text = report.to_markdown(analysis_from(corpus_dir))
    headline = text.splitlines()[2]
    assert "patterns explain" in headline
    assert "% of 4 incidents" in headline


def test_markdown_has_the_operational_sections(corpus_dir) -> None:
    text = report.to_markdown(analysis_from(corpus_dir))
    for section in (
        "## Triage decision tree",
        "## Signal x pattern matrix",
        "## Patterns in detail",
    ):
        assert section in text
    assert "```mermaid" in text


def test_markdown_flags_open_root_causes(corpus_dir) -> None:
    text = report.to_markdown(analysis_from(corpus_dir))
    assert "root cause still open" in text


def test_json_is_valid_and_stable(corpus_dir) -> None:
    payload = report.to_json(analysis_from(corpus_dir))
    data = json.loads(payload)
    assert data["incidents"] == 4
    assert 0.0 <= data["coverage"] <= 1.0
    assert data["patterns"]
    assert payload == report.to_json(analysis_from(corpus_dir))


def test_unexplained_incidents_are_listed(corpus_dir) -> None:
    (corpus_dir / "solo.md").write_text(
        "# odd one\n\nThe log volume hit 100% disk full overnight.\n", encoding="utf-8"
    )
    result = analysis_from(corpus_dir)
    assert [i.id for i in result.unexplained] == ["solo"]
    assert "Not explained by any pattern" in report.to_markdown(result)


def test_analysis_without_patterns_still_renders(tmp_path) -> None:
    directory = tmp_path / "c"
    directory.mkdir()
    (directory / "only.md").write_text("# solo\n\nPool at 80/80.\n", encoding="utf-8")
    result = analysis_from(directory)
    assert result.patterns == ()
    text = report.to_markdown(result)
    assert "0 patterns explain" in text
    assert "## Signal x pattern matrix" not in text
