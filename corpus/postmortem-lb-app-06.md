---
id: lb-app-06
title: Traffic imbalance plus an unguarded optional in the signing flow
date: 2026-01-07
severity: P1
service: svc-billing
tags: [postmortem, synthetic]
---

# Traffic imbalance plus an unguarded optional in the signing flow

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- Stickiness rehashed after the daily schedule restarted part of the fleet.
- Optional.get raised NoSuchElementException about 1200 times.
- A ClassCastException followed in the same code path.
- The partner callback was never sent, so the document was invalid downstream.

## Trigger

A discriminator mismatch made the lookup return empty for a valid party.

## Mitigation

DBA released stuck sessions while the team patched the lookup guard.

## Root cause

Root cause not addressed structurally - recurrence is expected.
