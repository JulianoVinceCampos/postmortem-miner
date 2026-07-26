---
id: retry-storm-10
title: Loop de retry de job agendado virou thundering herd
date: 2026-05-12
severity: P2
service: svc-ledger
tags: [postmortem, synthetic]
---

# Loop de retry de job agendado virou thundering herd

## Impact

Operacoes de clientes ficaram degradadas durante a janela do incidente.

## Observed signals

- CPU do banco alta por 45 minutos enquanto a CPU do host de batch ficou em 2%.
- Logs mostraram retry em loop sem backoff em tres timers agendados.
- A janela de batch noturno coincidiu com a primeira query pesada do dia.
- O thread pool do no de batch alcancou 1800 threads.

## Trigger

Um spike transitorio no banco fez cada timer falhar e reintentar de imediato.

## Mitigation

Reiniciamos apenas o processo de batch - sem reboot - e escalonamos o schedule.

## Root cause

Causa raiz estrutural nao tratada - a recorrencia deve continuar.
