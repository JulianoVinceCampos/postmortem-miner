---
id: pool-lock-08
title: Connection pool exhaustion with database lock contention
date: 2026-03-06
severity: P1
service: svc-intake
tags: [postmortem, synthetic]
---

# Connection pool exhaustion with database lock contention

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- Database CPU climbed to 96% and stayed there for 45 minutes.
- The JDBC pool sat at 40/40 with WaitCount above zero on every node.
- The DBA found sessions holding locks on the main write table.
- All nodes showed the same CPU profile, so this was not isolated to one host.

## Trigger

A cascading ORM flush turned one business operation into dozens of statements.

## Mitigation

Sequential restart of the application nodes plus the DBA killing locked sessions.

## Root cause

Root cause not addressed structurally - recurrence is expected.
