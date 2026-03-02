---
created: 2026-02-28T16:37:59.518Z
title: Add PodSecurity securityContext to deployment
area: deployment
files:
  - k8s/deployment.yaml
---

## Problem

Running `kubectl rollout restart deployment/mailroom -n mailroom` produces PodSecurity warnings because the deployment is missing a `securityContext` block. The `restricted` policy expects:

- `allowPrivilegeEscalation: false`
- `runAsNonRoot: true`
- `capabilities: { drop: ["ALL"] }`
- `seccompProfile: { type: RuntimeDefault }`

Not blocking — the deployment works fine — but the warnings are noisy and signal a best-practice gap.

## Solution

Add a `securityContext` block to the container spec in `k8s/deployment.yaml`. Could be done as a quick standalone fix or bundled into the Helm chart migration (where it would go into the Helm template instead).

```yaml
securityContext:
  allowPrivilegeEscalation: false
  runAsNonRoot: true
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```
