---
id: pool-lock-00
title: Esgotamento do pool de conexoes com contencao de locks no banco
date: 2026-01-14
severity: P1
service: svc-billing
tags: [postmortem, synthetic]
---

# Esgotamento do pool de conexoes com contencao de locks no banco

## Impact

Operacoes de clientes ficaram degradadas durante a janela do incidente.

## Observed signals

- CPU do banco subiu para 88% e ficou nesse patamar por 90 minutos.
- Pool JDBC em 80/80 com WaitCount acima de zero em todos os nos.
- O DBA identificou sessoes em lock na tabela principal de escrita.

## Trigger

Um flush em cascata do ORM transformou uma operacao em dezenas de statements.

## Mitigation

Restart sequencial dos nos da aplicacao e o DBA encerrando sessoes em lock.

## Root cause

Causa raiz estrutural nao tratada - a recorrencia deve continuar.
