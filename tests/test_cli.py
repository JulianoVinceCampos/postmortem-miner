"""CLI contract: exit codes and files on disk. Nothing clever."""

from __future__ import annotations

import json

import pytest

from postmortem_miner import cli


def test_mine_writes_both_outputs(corpus_dir, tmp_path, capsys) -> None:
    out = tmp_path / "nested" / "report.md"
    data = tmp_path / "nested" / "analysis.json"
    code = cli.main(["mine", str(corpus_dir), "--out", str(out), "--json", str(data)])
    assert code == 0
    assert out.read_text(encoding="utf-8").startswith("# Incident pattern analysis")
    assert json.loads(data.read_text(encoding="utf-8"))["incidents"] == 4
    stdout = capsys.readouterr().out
    assert "patterns explain" in stdout


def test_mine_prints_report_when_no_output_given(corpus_dir, capsys) -> None:
    assert cli.main(["mine", str(corpus_dir)]) == 0
    assert "## Triage decision tree" in capsys.readouterr().out


def test_quiet_suppresses_stdout(corpus_dir, tmp_path, capsys) -> None:
    out = tmp_path / "r.md"
    assert cli.main(["mine", str(corpus_dir), "--out", str(out), "--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_missing_corpus_exits_one(tmp_path, capsys) -> None:
    assert cli.main(["mine", str(tmp_path / "nope")]) == 1
    assert "error:" in capsys.readouterr().err


def test_corpus_without_signals_exits_one(tmp_path, capsys) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "a.md").write_text("# nothing\n", encoding="utf-8")
    assert cli.main(["mine", str(empty)]) == 1
    assert "no postmortem with recognisable signals" in capsys.readouterr().err


def test_signals_lists_every_token(capsys) -> None:
    assert cli.main(["signals"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "saturation.pool.exhausted" in lines
    assert len(lines) > 20


def test_classify_returns_a_label(corpus_dir, capsys) -> None:
    code = cli.main(
        [
            "classify",
            str(corpus_dir),
            "--signals",
            "saturation.pool.exhausted,store.lock.contention",
        ]
    )
    assert code == 0
    assert capsys.readouterr().out.strip()


def test_classify_warns_about_unknown_tokens(corpus_dir, capsys) -> None:
    cli.main(["classify", str(corpus_dir), "--signals", "made.up.token"])
    assert "unknown tokens ignored" in capsys.readouterr().err


def test_version_flag_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
