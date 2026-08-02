"""Signal extraction: free-form postmortem prose -> canonical tokens.

Design decision (see docs/adr/ADR-0002): the rule table is explicit regex, not a model.
Three reasons, all learned the hard way at 3am:

1. A triage tool has to explain itself. "matched `pool 80/80`" beats "cosine 0.82".
2. Postmortems are written by many people in two languages. A curated rule table is
   cheaper to correct than a training set is to rebuild.
3. It runs in milliseconds with no network, which is exactly when you need it.

Adding a signal means adding one row. That is the intended contribution path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from postmortem_miner.models import Signal, SignalKind

# (token, kind, pattern). Order matters only for readability; all rules are evaluated.
# Patterns are intentionally bilingual (pt-BR / en) because real corpora are.
#
# fmt: off - one rule per visual row is the whole point: adding a signal is a one-line
# contribution, and the auto-formatter would explode this into 5 lines per rule.
_RULES: tuple[tuple[str, SignalKind, str], ...] = (
    # --- resource -------------------------------------------------------------
    (
        "resource.cpu.saturated",
        SignalKind.RESOURCE,
        r"cpu[^.\n]{0,30}?(?:8\d|9\d|100)\s?%|cpu\s+(?:alta|saturad\w+|pegged|maxed)",
    ),
    (
        "resource.memory.exhausted",
        SignalKind.RESOURCE,
        r"\bOOM\b|OutOfMemory|heap\s+(?:estourou|cheio|exhaust\w+)|mem[oó]ria\s+esgotada",
    ),
    (
        "resource.gc.pressure",
        SignalKind.RESOURCE,
        r"full\s+gc|gc\s+(?:pause|longo|thrash\w+)|old\s+gen\s+(?:cheia|full)",
    ),
    (
        "resource.disk.pressure",
        SignalKind.RESOURCE,
        r"disco\s+(?:cheio|100)|disk\s+full|no\s+space\s+left",
    ),
    # --- saturation -----------------------------------------------------------
    (
        "saturation.pool.exhausted",
        SignalKind.SATURATION,
        r"pool[^.\n]{0,25}?(\d{1,4})\s*/\s*\1\b|pool\s+(?:esgotad\w+|cheio|exhaust\w+)",
    ),
    (
        "saturation.pool.wait",
        SignalKind.SATURATION,
        r"waitcount|wait\s+count|fila\s+de\s+espera|blocking\s?time",
    ),
    (
        "saturation.threads",
        SignalKind.SATURATION,
        r"threads?[^.\n]{0,20}?\d{3,}|thread\s+pool\s+(?:cheio|saturad\w+|exhaust\w+)",
    ),
    (
        "saturation.queue.backlog",
        SignalKind.SATURATION,
        r"backlog|fila\s+(?:acumul\w+|crescend\w+)|queue\s+depth",
    ),
    # --- data store -----------------------------------------------------------
    (
        "store.lock.contention",
        SignalKind.DATA_STORE,
        r"\block(?:s|ing)?\b|deadlock|conten[çc][ãa]o|sess[õo]es?\s+em\s+lock",
    ),
    ("store.rollback.long", SignalKind.DATA_STORE, r"rollback|desfazend\w+\s+transa|undo\s+log"),
    (
        "store.query.slow",
        SignalKind.DATA_STORE,
        r"quer(?:y|ies)\s+lent\w+|slow\s+quer|p9[59][^.\n]{0,20}(?:s|ms)\b",
    ),
    (
        "store.transaction.monolithic",
        SignalKind.DATA_STORE,
        r"transa[çc][ãa]o\s+(?:[úu]nica|gigante|monol[íi]tica)|single\s+(?:huge\s+)?transaction",
    ),
    # --- network --------------------------------------------------------------
    (
        "network.acl.block",
        SignalKind.NETWORK,
        r"security\s+group|\bacl\b|firewall|regra\s+de\s+entrada|ingress\s+rule",
    ),
    (
        "network.lb.imbalance",
        SignalKind.NETWORK,
        r"stickiness|desbalance\w+|imbalanc\w+|hash\s+(?:ip|de\s+target)",
    ),
    (
        "network.healthcheck.fail",
        SignalKind.NETWORK,
        r"health\s?check[^.\n]{0,20}(?:falh\w+|fail\w+|unhealthy)",
    ),
    (
        "network.timeout.external",
        SignalKind.NETWORK,
        r"timeout[^.\n]{0,30}(?:externo|fora\s+da\s+vpn|from\s+outside)|connection\s+timed?\s?out",
    ),
    # --- application ----------------------------------------------------------
    (
        "app.npe",
        SignalKind.APPLICATION,
        r"NoSuchElementException|NullPointerException|Optional\.get|unwrap\(\)\s+on\s+None",
    ),
    ("app.cast_error", SignalKind.APPLICATION, r"ClassCastException|TypeError|cannot\s+cast"),
    (
        "app.batch_error",
        SignalKind.APPLICATION,
        r"BatchUpdateException|batch\s+insert\s+(?:falh\w+|fail\w+)|-4329",
    ),
    (
        "app.retry_storm",
        SignalKind.APPLICATION,
        r"retry\s+(?:loop|storm|sem\s+backoff)|thundering\s+herd|reintent\w+\s+em\s+loop",
    ),
    (
        "app.error_swallowed",
        SignalKind.APPLICATION,
        r"catch\s*\(\s*Exception[^)]*\)\s*\{\s*\}|except\s*:\s*pass|erro\s+engolid\w+",
    ),
    (
        "app.callback_missing",
        SignalKind.APPLICATION,
        r"callback\s+(?:n[ãa]o\s+(?:enviad\w+|chegou)|missing)|retorno\s+n[ãa]o\s+enviad\w+",
    ),
    # --- lifecycle ------------------------------------------------------------
    (
        "lifecycle.deploy.recent",
        SignalKind.LIFECYCLE,
        r"deploy\s+(?:recente|de\s+ontem|[àa]s\s+\d)|rollout|release\s+publicad\w+"
        r"|\bdeployed\b|\bdeploy\b[^.\n]{0,25}(?:ontem|night|evening)",
    ),
    # `certifica[dt]` on purpose: certificaDo (pt) and certificaTe (en) differ by one
    # letter, and a rule that only spoke English silently dropped half the corpus.
    (
        "lifecycle.cert.expired",
        SignalKind.LIFECYCLE,
        r"certifica[dt]\w*[^.\n]{0,60}expir\w+|\b(?:ssl|tls)\b[^.\n]{0,30}expir\w+"
        r"|keystore\s+expir",
    ),
    (
        "lifecycle.schedule.window",
        SignalKind.LIFECYCLE,
        r"schedule|janela\s+de\s+(?:manuten|hor[áa]rio)|\bcron\b|start\s?/\s?stop",
    ),
    (
        "lifecycle.restart.reactive",
        SignalKind.LIFECYCLE,
        r"restart\s+(?:reativo|manual|sequencial)|reiniciad\w+\s+(?:manualmente|pelo\s+time)",
    ),
    # --- workload -------------------------------------------------------------
    (
        "workload.traffic.spike",
        SignalKind.WORKLOAD,
        r"pico\s+de\s+(?:tr[áa]fego|requisi|volume)|spike|surto\s+de\s+carga",
    ),
    (
        "workload.payload.large",
        SignalKind.WORKLOAD,
        r"\d{2,}\s?MB\b|payload\s+grande|arquivo\s+grande|remessa\s+(?:grande|de\s+\d{4,})",
    ),
    (
        "workload.batch.window",
        SignalKind.WORKLOAD,
        r"\bbatch\b|processamento\s+noturno|job\s+agendad\w+",
    ),
    # --- topology -------------------------------------------------------------
    (
        "topology.single_node",
        SignalKind.TOPOLOGY,
        r"(?:apenas|somente|s[óo])\s+(?:1|um)\s+n[óo]|isolad\w+\s+em\s+(?:um|1)\s+n[óo]"
        r"|single\s+node|only\s+(?:1|one)\s+node",
    ),
    (
        "topology.all_nodes",
        SignalKind.TOPOLOGY,
        r"todos\s+os\s+n[óo]s|toda\s+a\s+frota|all\s+nodes|fleet[- ]wide",
    ),
)
# fmt: on

_COMPILED: tuple[tuple[str, SignalKind, re.Pattern[str]], ...] = tuple(
    (token, kind, re.compile(pattern, re.IGNORECASE)) for token, kind, pattern in _RULES
)

_MAX_EVIDENCE = 160


def known_tokens() -> tuple[str, ...]:
    """Every token the extractor can emit. Used by tests and by `--explain`."""
    return tuple(token for token, _, _ in _RULES)


def kind_of(token: str) -> SignalKind | None:
    """The layer a token belongs to, or None if the extractor does not know the token.

    Exists so a caller can group tokens by layer without importing `_RULES`. The
    dashboard reads the taxonomy this way.
    """
    return next((kind for name, kind, _ in _RULES if name == token), None)


def _evidence(text: str, match: re.Match[str]) -> str:
    """Snippet around the match, trimmed to a readable single line.

    Edges are pulled back to word boundaries: evidence that starts mid-word reads like
    a bug even when the match is correct.
    """
    start = max(match.start() - 40, 0)
    end = min(match.end() + 40, len(text))
    if start > 0:
        space = text.find(" ", start, match.start())
        start = space + 1 if space != -1 else start
    if end < len(text):
        space = text.rfind(" ", match.end(), end)
        end = space if space != -1 else end
    snippet = " ".join(text[start:end].split())
    return snippet[:_MAX_EVIDENCE].strip()


def extract(text: str) -> tuple[Signal, ...]:
    """Extract canonical signals from postmortem prose.

    First match per token wins, so the strongest (earliest) evidence is the one kept.
    Output order is the rule-table order, which makes diffs between runs stable.
    """
    found: list[Signal] = []
    for token, kind, pattern in _COMPILED:
        match = pattern.search(text)
        if match is not None:
            found.append(Signal(token=token, kind=kind, evidence=_evidence(text, match)))
    return tuple(found)


def iter_by_kind(signals: Iterable[Signal], kind: SignalKind) -> Iterator[Signal]:
    return (s for s in signals if s.kind is kind)
