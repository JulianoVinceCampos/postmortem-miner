---
id: heap-oom-01
title: Estouro de heap ao processar payload muito grande
date: 2026-02-10
severity: P1
service: svc-billing
tags: [postmortem, synthetic]
---

# Estouro de heap ao processar payload muito grande

## Impact

Operacoes de clientes ficaram degradadas durante a janela do incidente.

## Observed signals

- O no node-1 lancou OOM as 12:17 ao parsear uma requisicao de 18 MB.
- Full GC rodou em sequencia e a old gen permaneceu cheia.
- Apenas 1 no foi afetado; o restante da frota seguiu atendendo.
- O arquivo de entrada trazia 26800 registros numa unica requisicao.

## Trigger

O documento inteiro e materializado em memoria antes de iniciar a persistencia.

## Mitigation

Reiniciamos o processo afetado e pedimos ao parceiro para dividir a remessa.

## Root cause

Causa raiz estrutural nao tratada - a recorrencia deve continuar.
