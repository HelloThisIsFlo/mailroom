---
created: 2026-03-02T12:18:52.153Z
title: Simplify Helm chart to vanilla textbook patterns
area: deployment
files:
  - helm/mailroom/templates/namespace.yaml
  - helm/mailroom/templates/_helpers.tpl
  - helm/mailroom/templates/deployment.yaml
  - helm/mailroom/templates/setup-job.yaml
---

## Problem

The Helm chart includes production hardening patterns that don't belong in a learning project: namespace.yaml in templates (anti-pattern — causes ownership conflicts), hardcoded securityContext/PSS helpers, readOnlyRootFilesystem with a /tmp emptyDir workaround. These obscure the standard Helm patterns the project is meant to teach.

Guiding principle: if it's not in a Helm beginner tutorial, it shouldn't be here. When something requires a hack or workaround, remove it rather than fix it.

## Solution

This is a **Helm learning project**. The chart should look like what you'd find in an official Helm tutorial or "getting started" guide — nothing more. If something requires a workaround or hack, remove it instead.

### Changes to make

**1. Delete `helm/mailroom/templates/namespace.yaml`**
- Namespaces don't belong in Helm templates — `--create-namespace` handles this
- No replacement needed, no PSS labels, no kubectl pre-flight

**2. Remove all `securityContext` from `_helpers.tpl`, `deployment.yaml`, and `setup-job.yaml`**
- Delete the `mailroom.podSecurityContext` and `mailroom.containerSecurityContext` template definitions from `_helpers.tpl`
- Remove all `securityContext:` blocks from `deployment.yaml` and `setup-job.yaml` (both pod-level and container-level)
- These are production hardening, not learning material

**3. Remove the `/tmp` emptyDir workaround from `deployment.yaml` and `setup-job.yaml`**
- The `tmp` volume and volumeMount only exist to work around `readOnlyRootFilesystem` (which we're removing)
- Delete the `tmp` emptyDir volume definition and its volumeMount from both files

**4. Create `scripts/deploy.sh` as a simple wrapper:**
```bash
helm upgrade --install mailroom "$CHART_DIR" \
  -f "$SECRETS_FILE" \
  -n mailroom --create-namespace
```

### What to keep (standard Helm patterns)

- `_helpers.tpl` name/label helpers — standard scaffolding
- `configmap.yaml` — standard
- `secret.yaml` — standard
- `deployment.yaml` — standard (after removing securityContext/tmp)
- `setup-job.yaml` as a Helm hook (`pre-install,pre-upgrade`) — good Helm pattern
- `NOTES.txt` — standard
- `values.yaml` / `Chart.yaml` — standard

### After changes

- Delete the namespace: `kubectl delete namespace mailroom`
- Redeploy: `./scripts/deploy.sh`
- Verify: `kubectl get all -n mailroom` — everything should come up clean

### Important

Do NOT add workarounds for any issues that come up. If something doesn't work with vanilla Helm, note it as a learning item rather than hacking around it.
