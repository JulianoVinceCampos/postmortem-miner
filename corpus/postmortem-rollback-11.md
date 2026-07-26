---
id: rollback-11
title: Rollback longo de uma transacao monolitica
date: 2026-06-03
severity: P1
service: svc-ledger
tags: [postmortem, synthetic]
---

# Rollback longo de uma transacao monolitica

## Impact

Operacoes de clientes ficaram degradadas durante a janela do incidente.

## Observed signals

- O banco parecia ocupado sem novas operacoes chegando - estava desfazendo trabalho.
- Uma transacao unica ficou aberta por 90 minutos antes de falhar.
- O crescimento do undo log acompanhou o volume ja escrito.

## Trigger

Uma requisicao equivale a uma transacao, e o custo da falha e proporcional ao volume.

## Mitigation

Liberamos CPU encerrando sessoes em espera e aguardamos. Forcar restart e pior.

## Root cause

Causa raiz estrutural nao tratada - a recorrencia deve continuar.
