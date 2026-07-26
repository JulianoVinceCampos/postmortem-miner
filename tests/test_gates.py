"""The CI gates are tested too. An untested gate is theatre."""

from __future__ import annotations

import pytest

import coverage_ratchet
import gen_corpus
import sanitize_scan

# --- sanitize gate --------------------------------------------------------------
#
# The fixtures below are assembled at runtime from harmless fragments instead of being
# written as literals. Two reasons, and the second is the important one:
#
# 1. The repository then contains no leak-shaped string at all, so scanning the repo is
#    clean by construction - no waiver list to maintain and nothing to hide behind.
# 2. A fixture file full of realistic-looking identifiers is exactly how a real value
#    eventually gets pasted in "just for a test" and shipped.
#
# The scanner sees the assembled value at runtime, so the rules are still exercised.

INSTANCE_ID = "i-0" + "abc12345def67890"
ACCOUNT_ID = "1234" + "5678" + "9012"
CORP_HOST = "app." + "crdc" + ".tools"
TAX_ID = "12.345." + "678/0001-95"
PRIVATE_IP = ".".join(["10", "0", "0", "150"])


@pytest.mark.parametrize(
    ("content", "rule"),
    [
        (f"instance = '{INSTANCE_ID}'", "aws-instance-id"),
        (f"account: {ACCOUNT_ID}", "aws-account-id"),
        (f"host: {CORP_HOST}", "corp-domain"),
        (f"cnpj: {TAX_ID}", "brazilian-tax-id"),
        (f"endpoint: {PRIVATE_IP}", "private-ip"),
    ],
)
def test_sanitize_catches_corporate_context(tmp_path, content: str, rule: str) -> None:
    target = tmp_path / "leak.py"
    target.write_text(content + "\n", encoding="utf-8")
    findings = sanitize_scan.scan([target])
    assert [f[2] for f in findings] == [rule]


@pytest.mark.parametrize(
    "content",
    [
        "account: 000000000000",
        "instance = 'i-0EXAMPLE'",
        "host: api.example.com",
        "endpoint: 203.0.113.10",
        "endpoint: 198.51.100.7",
        "local = '127.0.0.1'",
    ],
)
def test_sanitize_accepts_documented_placeholders(tmp_path, content: str) -> None:
    target = tmp_path / "ok.py"
    target.write_text(content + "\n", encoding="utf-8")
    assert sanitize_scan.scan([target]) == []


def test_sanitize_respects_inline_waiver(tmp_path) -> None:
    target = tmp_path / "waived.py"
    waiver = "sanitize" + "-ok"
    target.write_text(f"ip = '{PRIVATE_IP}'  # {waiver}: rule fixture\n", encoding="utf-8")
    assert sanitize_scan.scan([target]) == []


def test_sanitize_skips_binary_and_unknown_suffixes(tmp_path) -> None:
    (tmp_path / "blob.png").write_bytes(b"\x89PNG\r\n\x1a\n " + INSTANCE_ID.encode())
    assert sanitize_scan.scan([tmp_path]) == []


def test_sanitize_reports_line_numbers(tmp_path) -> None:
    target = tmp_path / "multi.md"
    target.write_text(f"clean line\nanother\naccount: {ACCOUNT_ID}\n", encoding="utf-8")
    findings = sanitize_scan.scan([target])
    assert findings[0][1] == 3


def test_sanitize_main_returns_two_for_missing_path(tmp_path, capsys) -> None:
    assert sanitize_scan.main(["prog", str(tmp_path / "nope")]) == 2
    assert "path not found" in capsys.readouterr().err


def test_sanitize_main_returns_one_on_finding(tmp_path) -> None:
    target = tmp_path / "leak.md"
    target.write_text(f"account: {ACCOUNT_ID}\n", encoding="utf-8")
    assert sanitize_scan.main(["prog", str(target)]) == 1


def test_sanitize_main_returns_zero_when_clean(tmp_path) -> None:
    target = tmp_path / "clean.md"
    target.write_text("nothing to see\n", encoding="utf-8")
    assert sanitize_scan.main(["prog", str(target)]) == 0


def test_repository_itself_is_clean() -> None:
    """The gate must pass on this very repo, with no waiver in sight."""
    assert sanitize_scan.scan([sanitize_scan.ROOT]) == []


# --- corpus generator -----------------------------------------------------------


def test_corpus_is_deterministic_for_a_seed(tmp_path) -> None:
    """The README numbers depend on this."""
    first = tmp_path / "a"
    second = tmp_path / "b"
    gen_corpus.generate(first, count=8, seed=7)
    gen_corpus.generate(second, count=8, seed=7)
    for left, right in zip(sorted(first.iterdir()), sorted(second.iterdir()), strict=True):
        assert left.name == right.name
        assert left.read_bytes() == right.read_bytes()


def test_corpus_includes_one_off_incidents(tmp_path) -> None:
    written = gen_corpus.generate(tmp_path, count=8, seed=1)
    assert len(written) == 8 + len(gen_corpus.ANECDOTES)
    assert any("oneoff" in path.name for path in written)


def test_corpus_regeneration_removes_stale_files(tmp_path) -> None:
    gen_corpus.generate(tmp_path, count=16, seed=3)
    before = len(list(tmp_path.glob("postmortem-*.md")))
    gen_corpus.generate(tmp_path, count=4, seed=3)
    after = len(list(tmp_path.glob("postmortem-*.md")))
    assert after < before


def test_generated_corpus_passes_the_sanitize_gate(tmp_path) -> None:
    """The corpus is the most likely place for a leak to hide."""
    gen_corpus.generate(tmp_path, count=18, seed=7)
    assert sanitize_scan.scan([tmp_path]) == []


# --- coverage ratchet -----------------------------------------------------------


def _write_report(path, rate: float) -> None:
    path.write_text(
        f'<?xml version="1.0"?>\n<coverage line-rate="{rate}"></coverage>\n', encoding="utf-8"
    )


def test_ratchet_reads_line_rate(tmp_path) -> None:
    report = tmp_path / "coverage.xml"
    _write_report(report, 0.8765)
    assert coverage_ratchet.read_coverage(report) == pytest.approx(87.65)


def test_ratchet_rejects_report_without_rate(tmp_path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text('<?xml version="1.0"?>\n<coverage></coverage>\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line-rate"):
        coverage_ratchet.read_coverage(report)


def test_ratchet_missing_floor_file_is_zero(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(coverage_ratchet, "FLOOR_FILE", tmp_path / "absent")
    assert coverage_ratchet.read_floor() == 0.0


def test_ratchet_reads_existing_floor(monkeypatch, tmp_path) -> None:
    floor = tmp_path / "floor"
    floor.write_text("91.50\n", encoding="utf-8")
    monkeypatch.setattr(coverage_ratchet, "FLOOR_FILE", floor)
    assert coverage_ratchet.read_floor() == pytest.approx(91.5)


def test_ratchet_fails_on_regression(monkeypatch, tmp_path, capsys) -> None:
    floor = tmp_path / "floor"
    floor.write_text("95.00\n", encoding="utf-8")
    report = tmp_path / "coverage.xml"
    _write_report(report, 0.80)
    monkeypatch.setattr(coverage_ratchet, "FLOOR_FILE", floor)
    monkeypatch.setattr("sys.argv", ["prog", "--report", str(report)])
    assert coverage_ratchet.main() == 1
    assert "REGRESSION" in capsys.readouterr().out


def test_ratchet_raises_the_floor_only_when_asked(monkeypatch, tmp_path, capsys) -> None:
    floor = tmp_path / "floor"
    floor.write_text("80.00\n", encoding="utf-8")
    report = tmp_path / "coverage.xml"
    _write_report(report, 0.93)
    monkeypatch.setattr(coverage_ratchet, "FLOOR_FILE", floor)

    monkeypatch.setattr("sys.argv", ["prog", "--report", str(report)])
    assert coverage_ratchet.main() == 0
    assert floor.read_text(encoding="utf-8").strip() == "80.00"
    assert "can be raised" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["prog", "--report", str(report), "--update"])
    assert coverage_ratchet.main() == 0
    assert floor.read_text(encoding="utf-8").strip() == "93.00"


def test_ratchet_missing_report_is_a_usage_error(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--report", str(tmp_path / "absent.xml")])
    assert coverage_ratchet.main() == 2
    assert "not found" in capsys.readouterr().out
