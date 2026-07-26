---
id: heap-oom-17
title: Heap exhaustion while handling an oversized payload
date: 2026-06-05
severity: P2
service: svc-registry
tags: [postmortem, synthetic]
---

# Heap exhaustion while handling an oversized payload

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- Node node-2 threw OOM at 18:17 while parsing a 44 MB request.
- Full GC ran back to back and old gen stayed full.
- Only 1 node was affected; the rest of the fleet kept serving traffic.
- The inbound file carried 8400 records in a single request.

## Trigger

The whole document is materialised in memory before persistence begins.

## Mitigation

Restarted the affected process and asked the partner to split the batch.

## Root cause

Root cause not addressed structurally - recurrence is expected.
