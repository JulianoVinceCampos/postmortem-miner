---
id: slow-query-15
title: Slow queries after a statistics refresh
date: 2026-04-20
severity: P1
service: svc-notify
tags: [postmortem, synthetic]
---

# Slow queries after a statistics refresh

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- Query p99 went from 60 ms to 2600 ms right after the maintenance window.
- Slow query log filled with the same three statements.
- Database CPU reached 92% without any pool saturation.
- A release had been deployed the evening before.

## Trigger

A stale execution plan survived the statistics refresh.

## Mitigation

Forced a plan invalidation. Root cause addressed with a scheduled refresh job.

## Root cause

Root cause addressed.
