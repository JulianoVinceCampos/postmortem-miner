#!/usr/bin/env python3
"""Block corporate context from ever reaching a public commit.

Runs on pre-commit and in CI as the first job. Zero dependencies so it works on a
clean machine with nothing installed but Python.

Why this exists: this project was born out of work on private production systems. A
leaked hostname or account id in a public git history is permanent - you cannot
un-publish it. So the check runs before anything else, and it fails closed.

    python3 tools/sanitize_scan.py            # scan tracked-ish files
    python3 tools/sanitize_scan.py path ...   # scan specific paths

Exit 0 clean, 1 findings, 2 usage error.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Rule files legitimately contain the patterns themselves.
SELF_EXEMPT = {"tools/sanitize_scan.py", ".semgrep/no-corp-leak.yml", ".gitleaks.toml"}

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    "node_modules",
    "dist",
    "build",
    "out",
    "htmlcov",
}
SCAN_SUFFIXES = {
    ".py",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".cfg",
    ".ini",
    ".txt",
    ".sh",
    ".go",
    ".java",
    ".xml",
    ".properties",
    "",
}

# Documented placeholders. Anything here is safe by construction.
ALLOWLIST = (
    "000000000000",
    "i-0EXAMPLE",
    "example.com",
    "users.noreply.github.com",
    "203.0.113.",  # RFC 5737 TEST-NET-3
    "198.51.100.",  # RFC 5737 TEST-NET-2
    "192.0.2.",  # RFC 5737 TEST-NET-1
    "127.0.0.1",
    "0.0.0.0",
)

RULES: tuple[tuple[str, str, str], ...] = (
    (
        "aws-instance-id",
        r"\bi-0[a-f0-9]{8,17}\b",
        "real AWS instance id - use i-0EXAMPLE",
    ),
    (
        "aws-account-id",
        r"\b\d{12}\b",
        "12-digit account id - use 000000000000",
    ),
    (
        "corp-domain",
        r"(?i)\b[a-z0-9-]+\.(?:crdc\.(?:com\.br|me|tools)|globalhitss\.com\.br)\b",
        "corporate domain - use example.com",
    ),
    (
        "brazilian-tax-id",
        r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
        "CNPJ/CPF shaped number - generate a synthetic one",
    ),
    (
        "private-ip",
        r"\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b",
        "private IP - use the RFC 5737 ranges",
    ),
    (
        "internal-hostname",
        r"(?i)\b(?:wildfly-[0-9]|db2_[ac]|formaliza[a-z]*o|escritura[a-z]*o)\b",
        "internal host/product name - describe the architecture pattern instead",
    ),
)

COMPILED = tuple((name, re.compile(pattern), hint) for name, pattern, hint in RULES)


def _iter_files(targets: list[Path]) -> Iterator[Path]:
    for target in targets:
        if target.is_file():
            yield target
            continue
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in SCAN_SUFFIXES:
                yield path


def _allowlisted(line: str) -> bool:
    """A line is waived by a documented placeholder or an explicit `sanitize-ok`."""
    if any(token in line for token in ALLOWLIST):
        return True
    return "sanitize-ok" in line


def scan(targets: list[Path]) -> list[tuple[Path, int, str, str, str]]:
    findings: list[tuple[Path, int, str, str, str]] = []
    for path in _iter_files(targets):
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            relative = path.as_posix()
        if relative in SELF_EXEMPT:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            for name, pattern, hint in COMPILED:
                match = pattern.search(line)
                if match and not _allowlisted(line):
                    findings.append((path, number, name, match.group(0)[:60], hint))
    return findings


def main(argv: list[str]) -> int:
    targets = [Path(arg) for arg in argv[1:]] or [ROOT]
    for target in targets:
        if not target.exists():
            print(f"error: path not found: {target}", file=sys.stderr)
            return 2

    findings = scan(targets)
    if not findings:
        print("sanitize: clean")
        return 0

    print(f"sanitize: {len(findings)} finding(s)\n", file=sys.stderr)
    for path, number, name, snippet, hint in findings:
        location = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path
        print(f"  {location}:{number} [{name}] {snippet!r}\n      {hint}", file=sys.stderr)
    print(
        "\nIf a match is a deliberate placeholder, add it to ALLOWLIST or end the line "
        "with a `sanitize-ok` comment explaining why.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
