"""Shared fixtures."""

from __future__ import annotations

import pytest

POOL_LOCK_PT = """---
id: sample-01
title: Esgotamento de pool com locks
date: 2026-03-14
severity: P1
service: svc-ledger
---

# Esgotamento de pool com locks

## Observed signals

- CPU do banco subiu para 98% e ficou nesse patamar por 60 minutos.
- Pool JDBC em 80/80 com WaitCount acima de zero em todos os nos.
- O DBA identificou sessoes em lock na tabela principal.

## Mitigation

Restart sequencial dos nos e o DBA encerrando sessoes em lock.

## Root cause

Causa raiz estrutural nao tratada - a recorrencia deve continuar.
"""

HEAP_EN = """# Heap exhaustion on one node

## Observed signals

- Node node-2 threw OOM at 16:17 while parsing a 31 MB request.
- Full GC ran back to back and old gen stayed full.
- Only 1 node was affected.

## Root cause

Root cause addressed.
"""


@pytest.fixture
def pool_lock_text() -> str:
    return POOL_LOCK_PT


@pytest.fixture
def heap_text() -> str:
    return HEAP_EN


@pytest.fixture
def corpus_dir(tmp_path):
    """A tiny two-family corpus: two pool incidents, two heap incidents."""
    directory = tmp_path / "corpus"
    directory.mkdir()
    for index in range(2):
        (directory / f"pool-{index}.md").write_text(POOL_LOCK_PT, encoding="utf-8")
        (directory / f"heap-{index}.md").write_text(HEAP_EN, encoding="utf-8")
    return directory
