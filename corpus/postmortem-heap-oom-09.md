---
id: heap-oom-09
title: Estouro de heap ao processar payload muito grande
date: 2026-04-04
severity: P1
service: svc-notify
tags: [postmortem, synthetic]
---

# Estouro de heap ao processar payload muito grande

## Impact

Operacoes de clientes ficaram degradadas durante a janela do incidente.

## Observed signals

- O no node-5 lancou OOM as 14:17 ao parsear uma requisicao de 24 MB.
- Full GC rodou em sequencia e a old gen permaneceu cheia.
- Apenas 1 no foi afetado; o restante da frota seguiu atendendo.

## Trigger

O documento inteiro e materializado em memoria antes de iniciar a persistencia.

## Mitigation

Reiniciamos o processo afetado e pedimos ao parceiro para dividir a remessa.

## Root cause

Causa raiz estrutural nao tratada - a recorrencia deve continuar.
