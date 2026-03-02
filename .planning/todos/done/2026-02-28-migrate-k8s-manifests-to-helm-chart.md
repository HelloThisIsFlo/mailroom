---
created: 2026-02-28T02:09:40.445Z
title: Migrate k8s manifests to Helm chart
area: deployment
files:
  - k8s/
  - helm/mailroom/
---

## Problem

Plain k8s/ manifests work but require duplicated Job files for variants (e.g., setup-job-dry-run.yaml vs setup-job-apply.yaml). Secrets live in a separate gitignored YAML which is easy to forget. No built-in way to parameterize config per environment.

## Solution

Clean up the learning exercise in `helm/mailroom/` and promote it to the primary deployment method:
- Split secrets into a gitignored `secrets-values.yaml` (pass via `helm install -f`)
- Replace plain `k8s/` manifests with the Helm chart
- Setup Job uses `setup.enabled` and `setup.apply` flags — one template, no duplication
- Add `secrets-values.yaml` to `.gitignore`

### Public/private config split

Helm also solves the "default config in repo, custom overrides locally" problem:
- `values.yaml` is committed with sensible defaults (no secrets, no custom categories)
- Private overrides (secrets, Billboard/Truck categories) go in a gitignored file
- Deploy with: `helm install -f values.yaml -f my-overrides.yaml` — later files win
- This pairs naturally with the YAML config migration (see: migrate-from-env-var-config-to-config-yaml todo)

### K8s Job experiment (reverted)

We tried dedicated Job manifests (setup-job-dry-run.yaml, setup-job-apply.yaml) but reverted them — too verbose for daily use. `kubectl exec -it deploy/mailroom -- python -m mailroom setup` is simpler. In Helm, the Job would be `--set setup.enabled=true` which is cleaner. See git history for the experiment (commit + revert pair).
