---
id: cert-04
title: Expired TLS certificate took the public endpoint down
date: 2026-05-03
severity: P2
service: svc-registry
tags: [postmortem, synthetic]
---

# Expired TLS certificate took the public endpoint down

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- The certificate on the edge listener had expired 2 days earlier.
- Health check failures started at the same minute for every target.
- Clients outside the VPN saw connection timed out; internal calls were fine.
- No deploy had happened in the previous week.

## Trigger

Renewal was manual and the calendar reminder had no owner.

## Mitigation

Replaced the keystore and reloaded the listener. Root cause addressed: renewal automated.

## Root cause

Root cause addressed.
