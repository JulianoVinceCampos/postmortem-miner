---
id: rollback-03
title: Long rollback of a monolithic transaction
date: 2026-04-17
severity: P1
service: svc-intake
tags: [postmortem, synthetic]
---

# Long rollback of a monolithic transaction

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- The database looked busy with no new operations arriving - it was undoing work.
- A single huge transaction had been open for 60 minutes before failing.
- Undo log growth tracked the volume already written.

## Trigger

One request equals one transaction, so failure cost is proportional to volume.

## Mitigation

Freed CPU by ending waiting sessions and waited it out. Forcing a restart is worse.

## Root cause

Root cause not addressed structurally - recurrence is expected.
