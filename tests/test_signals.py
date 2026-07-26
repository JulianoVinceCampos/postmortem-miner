"""Signal extraction is the foundation: if it drifts, every pattern shifts with it."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from postmortem_miner import signals
from postmortem_miner.models import SignalKind


def tokens(text: str) -> set[str]:
    return {signal.token for signal in signals.extract(text)}


def test_known_tokens_are_unique_and_dotted() -> None:
    known = signals.known_tokens()
    assert len(known) == len(set(known)), "duplicate token in the rule table"
    assert all("." in token for token in known)


def test_extracts_pool_and_lock_signals(pool_lock_text: str) -> None:
    found = tokens(pool_lock_text)
    assert "saturation.pool.exhausted" in found
    assert "saturation.pool.wait" in found
    assert "store.lock.contention" in found
    assert "resource.cpu.saturated" in found


def test_extracts_heap_signals(heap_text: str) -> None:
    found = tokens(heap_text)
    assert "resource.memory.exhausted" in found
    assert "resource.gc.pressure" in found
    assert "topology.single_node" in found


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "O certificado do listener de borda havia expirado 2 dias antes.",
            "lifecycle.cert.expired",
        ),
        (
            "The certificate on the edge listener had expired three days earlier.",
            "lifecycle.cert.expired",
        ),
        ("A release had been deployed the evening before.", "lifecycle.deploy.recent"),
        ("Uma transacao unica ficou aberta por 45 minutos.", "store.transaction.monolithic"),
        ("retry loop with no backoff across three timers", "app.retry_storm"),
        ("The security group ingress rule did not cover the subnets.", "network.acl.block"),
    ],
)
def test_bilingual_rules(text: str, expected: str) -> None:
    """The corpus is written by humans in two languages; the rules must be too."""
    assert expected in tokens(text)


def test_pool_rule_requires_matching_numbers() -> None:
    """`pool 80/80` is saturation. `pool 12/80` is a healthy Tuesday."""
    assert "saturation.pool.exhausted" in tokens("pool at 80/80 on every node")
    assert "saturation.pool.exhausted" not in tokens("pool at 12/80, plenty of headroom")


def test_first_match_wins_and_order_is_stable(pool_lock_text: str) -> None:
    first = signals.extract(pool_lock_text)
    second = signals.extract(pool_lock_text)
    assert [s.token for s in first] == [s.token for s in second]
    assert len({s.token for s in first}) == len(first), "token emitted twice"


def test_evidence_is_single_line_and_bounded(pool_lock_text: str) -> None:
    for signal in signals.extract(pool_lock_text):
        assert "\n" not in signal.evidence
        assert len(signal.evidence) <= 160
        assert signal.evidence == signal.evidence.strip()


def test_evidence_does_not_start_mid_word() -> None:
    """Evidence starting mid-word reads like a bug even when the match is right."""
    text = (
        "Uma linha bem longa de contexto antes do sinal para forcar o recorte da janela, "
        "porque a CPU do banco subiu para 98% durante a janela e ficou nesse patamar."
    )
    signal = next(s for s in signals.extract(text) if s.token == "resource.cpu.saturated")
    words = text.split()
    assert signal.evidence.split()[0] in words, "evidence starts in the middle of a word"


def test_iter_by_kind(pool_lock_text: str) -> None:
    extracted = signals.extract(pool_lock_text)
    saturation = list(signals.iter_by_kind(extracted, SignalKind.SATURATION))
    assert saturation
    assert all(s.kind is SignalKind.SATURATION for s in saturation)


@settings(max_examples=150, deadline=None)
@given(st.text(max_size=400))
def test_extract_never_raises_on_arbitrary_text(text: str) -> None:
    """Postmortems are user input. A parser that crashes on odd bytes is useless."""
    result = signals.extract(text)
    assert all(token in signals.known_tokens() for token in (s.token for s in result))
