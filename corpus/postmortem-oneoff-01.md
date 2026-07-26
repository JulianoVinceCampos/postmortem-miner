---
id: oneoff-01
title: Disk filled on the log volume
date: 2026-03-14
severity: P2
service: svc-billing
tags: [postmortem, synthetic]
---

# Disk filled on the log volume

## Impact

Limited impact, single occurrence.

## Observed signals

- The log volume hit 100% disk full after debug logging was left enabled overnight. No space left on device appeared in the application log. Root cause addressed: log rotation restored and the debug flag reverted.

## Trigger

Single occurrence, no recurring trigger identified.

## Mitigation

Handled inline by the on-call engineer.

## Root cause

Root cause addressed.
