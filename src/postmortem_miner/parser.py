"""Postmortem markdown -> Incident.

Deliberately forgiving. A parser that rejects a postmortem because someone typed
`Severidade:` instead of `severity:` is a parser nobody runs. Every field is optional;
only the body text is required, because that is where the signals live.

Frontmatter support is a small stdlib-only subset of YAML (scalars, inline lists,
block lists). That keeps the package at zero runtime dependencies, which is the whole
point of being able to run it from a locked-down box during an incident.
"""

from __future__ import annotations

import re
from pathlib import Path

from postmortem_miner.models import Incident
from postmortem_miner.signals import extract

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_DATE = re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})|(\d{2})[-/](\d{2})[-/](\d{4})")

# Section aliases, bilingual. Longest match wins so "causa raiz tratada" does not
# get swallowed by "causa raiz".
_SECTIONS: dict[str, tuple[str, ...]] = {
    "trigger": ("gatilho", "trigger", "causa raiz", "root cause", "o que aconteceu"),
    "mitigation": ("mitiga", "mitigation", "contorno", "workaround", "a[çc][ãa]o tomada"),
}

_ADDRESSED = re.compile(
    r"causa\s+raiz\s+(?:tratada|corrigida|resolvida)|root\s+cause\s+(?:fixed|addressed)",
    re.IGNORECASE,
)
_NOT_ADDRESSED = re.compile(
    r"causa\s+raiz\s+(?:n[ãa]o\s+tratada|estrutural\s+n[ãa]o\s+tratada|pendente)"
    r"|root\s+cause\s+not\s+addressed",
    re.IGNORECASE,
)


def _parse_frontmatter(raw: str) -> dict[str, str]:
    """Minimal YAML subset: `key: value`, `key: [a, b]`, and `-` block lists."""
    data: dict[str, str] = {}
    current_key: str | None = None
    collected: list[str] = []

    def flush() -> None:
        if current_key and collected:
            data[current_key] = ", ".join(collected)

    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and current_key:
            collected.append(line.lstrip()[2:].strip().strip("\"'"))
            continue
        if ":" not in line:
            continue
        flush()
        collected = []
        key, _, value = line.partition(":")
        current_key = key.strip().lower()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1]
            data[current_key] = ", ".join(
                v.strip().strip("\"'") for v in value.split(",") if v.strip()
            )
            current_key = None
        elif value:
            data[current_key] = value.strip("\"'")
            current_key = None
    flush()
    return data


def _first_heading(body: str) -> str | None:
    match = _HEADING.search(body)
    return match.group(1).strip() if match else None


def _section_text(body: str, aliases: tuple[str, ...]) -> str | None:
    """Return the paragraph under the first heading matching any alias."""
    headings = list(_HEADING.finditer(body))
    for index, heading in enumerate(headings):
        title = heading.group(1).lower()
        if any(re.search(alias, title, re.IGNORECASE) for alias in aliases):
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
            text = " ".join(body[start:end].split())
            if text:
                return text[:400]
    return None


def _guess_date(data: dict[str, str], body: str, name: str) -> str | None:
    for candidate in (data.get("date"), data.get("data"), name, body[:400]):
        if not candidate:
            continue
        match = _DATE.search(candidate)
        if match:
            if match.group(1):
                return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            return f"{match.group(6)}-{match.group(5)}-{match.group(4)}"
    return None


def parse_text(text: str, *, source: str = "<memory>", incident_id: str | None = None) -> Incident:
    """Parse postmortem content into an Incident. Never raises on odd input."""
    frontmatter: dict[str, str] = {}
    body = text
    match = _FRONTMATTER.match(text)
    if match:
        frontmatter = _parse_frontmatter(match.group(1))
        body = text[match.end() :]

    stem = Path(source).stem
    root_cause_addressed = bool(_ADDRESSED.search(body)) and not _NOT_ADDRESSED.search(body)

    return Incident(
        id=incident_id or frontmatter.get("id") or stem or "unknown",
        title=frontmatter.get("title") or _first_heading(body) or stem,
        source=source,
        occurred_on=_guess_date(frontmatter, body, stem),
        severity=frontmatter.get("severity") or frontmatter.get("severidade"),
        service=frontmatter.get("service") or frontmatter.get("servico"),
        trigger=_section_text(body, _SECTIONS["trigger"]),
        mitigation=_section_text(body, _SECTIONS["mitigation"]),
        root_cause_addressed=root_cause_addressed,
        signals=extract(body),
    )


def parse_file(path: Path) -> Incident:
    return parse_text(path.read_text(encoding="utf-8", errors="replace"), source=str(path))


def parse_corpus(directory: Path, *, glob: str = "*.md") -> list[Incident]:
    """Parse every markdown file under `directory`, sorted for reproducible output."""
    if not directory.is_dir():
        raise NotADirectoryError(f"corpus directory not found: {directory}")
    incidents = [parse_file(path) for path in sorted(directory.rglob(glob))]
    return [i for i in incidents if i.signals]
