---
id: pool-lock-16
title: Connection pool exhaustion with database lock contention
date: 2026-05-15
severity: P1
service: svc-ledger
tags: [postmortem, synthetic]
---

# Connection pool exhaustion with database lock contention

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- Database CPU climbed to 92% and stayed there for 35 minutes.
- The JDBC pool sat at 80/80 with WaitCount above zero on every node.
- The DBA found sessions holding locks on the main write table.

## Trigger

A cascading ORM flush turned one business operation into dozens of statements.

## Mitigation

Sequential restart of the application nodes plus the DBA killing locked sessions.

## Root cause

Root cause not addressed structurally - recurrence is expected.
