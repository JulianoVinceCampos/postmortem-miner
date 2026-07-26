---
id: acl-13
title: External access blocked by a security group range gap
date: 2026-02-20
severity: P1
service: svc-billing
tags: [postmortem, synthetic]
---

# External access blocked by a security group range gap

## Impact

Customer operations were degraded for the duration of the incident.

## Observed signals

- The app answered through the VPN but timed out from outside.
- Load balancer health check was failing from the subnet range 203.0.113.0/24.
- The security group ingress rule did not cover the balancer subnets.
- No application error appeared in the logs at all.

## Trigger

Client IP preservation exposed source addresses no ingress rule accepted.

## Mitigation

Allowed the balancer subnets on the required ports. Root cause addressed.

## Root cause

Root cause addressed.
