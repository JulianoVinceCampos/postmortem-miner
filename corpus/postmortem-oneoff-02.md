---
id: oneoff-02
title: Backlog after a partner outage
date: 2026-04-14
severity: P2
service: svc-intake
tags: [postmortem, synthetic]
---

# Backlog after a partner outage

## Impact

Limited impact, single occurrence.

## Observed signals

- A partner endpoint was unavailable for two hours and the outbound queue depth grew steadily. Nothing was saturated locally. The backlog drained on its own once the partner recovered. Root cause addressed on the partner side.

## Trigger

Single occurrence, no recurring trigger identified.

## Mitigation

Handled inline by the on-call engineer.

## Root cause

Root cause addressed.
