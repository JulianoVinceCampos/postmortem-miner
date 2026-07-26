---
id: retry-storm-02
title: Scheduled job retry loop turned into a thundering herd
date: 2026-03-20
severity: P1
service: svc-notify
tags: [postmortem, synthetic]
---

# Scheduled job retry loop turned into a thundering herd

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- Database CPU stayed high for 60 minutes while the batch host CPU was 2%.
- Logs showed a retry loop with no backoff across three scheduled timers.
- The nightly batch window overlapped with the first heavy query of the day.
- Thread pool on the batch node reached 1800 threads.

## Trigger

A transient database spike made every timer fail and immediately retry.

## Mitigation

Restarted the batch process only - no reboot - and staggered the schedule.

## Root cause

Root cause not addressed structurally - recurrence is expected.
