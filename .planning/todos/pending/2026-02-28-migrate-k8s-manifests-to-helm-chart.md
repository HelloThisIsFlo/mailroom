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
- Remove `kustomize/` learning exercise after migration
- Add `secrets-values.yaml` to `.gitignore`
