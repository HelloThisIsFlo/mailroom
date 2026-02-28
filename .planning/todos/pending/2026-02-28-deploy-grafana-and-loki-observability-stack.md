---
created: 2026-02-28T16:50:00.000Z
title: Deploy Grafana and Loki observability stack
area: deployment
files: []
---

## Problem

Mailroom produces structured JSON logs but there's no good way to view, search, or filter them. `kubectl logs` shows raw JSON which is hard to scan — the `already_grouped` warning that triggered this todo was buried in a wall of `poll_completed` lines. k9s shows logs but doesn't parse JSON either.

## Solution

Deploy the Grafana + Loki stack on the cluster to get a proper log query UI.

### What to deploy

1. **Loki** — log aggregation backend. Stores and indexes structured JSON logs. Use `SingleBinary` deployment mode (lightweight, fine for a small cluster).
2. **Grafana** — query UI. Connect Loki as a data source. Query with LogQL: `{namespace="mailroom"} | json | level="warning"`.

Both are free, open-source, and deployed via Helm charts from `grafana/helm-charts`.

### Why this matters

- Query by any JSON field: `event`, `sender`, `level`, `component`
- Time-range filtering, live tail, saved queries
- Directly transferable to work — this is the industry-standard stack (Grafana LGTM)
- Foundation for future additions: Prometheus (metrics), Tempo (traces/OpenTelemetry)

### Future expansion path (not now)

- **Prometheus** — `kube-prometheus-stack` Helm chart. Gives CPU, memory, pod metrics out of the box. Later, add custom Mailroom metrics (`mailroom_emails_triaged_total`, `mailroom_poll_duration_seconds`) via a `/metrics` endpoint.
- **Tempo** — distributed tracing backend. Pair with `opentelemetry-python` to trace poll cycles (JMAP calls, CardDAV calls as spans). Only interesting with multiple services.
- All three plug into the same Grafana UI — logs ↔ metrics ↔ traces linked together.

### Prerequisite

See separate todo: "Reorder JSON log fields for scannability" — small code change to `logging.py`, can be done independently and much earlier.

### Talos OS documentation

**Important:** When deploying Grafana + Loki, document the process in the Talos OS repo (the cluster configuration repo). The Helm values, namespace setup, persistent volume config, and any Talos-specific considerations (storage classes, ingress rules) should live there — not in this repo. This repo only cares about the Mailroom logging format; the infrastructure belongs in Talos OS.

Reminder for the agent tackling this: check the Talos OS repo for existing monitoring/infrastructure patterns, and migrate/document the Grafana + Loki Helm values there alongside the other cluster services.

### Helm commands (reference)

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install loki grafana/loki \
  --namespace monitoring --create-namespace \
  --set deploymentMode=SingleBinary \
  --set singleBinary.replicas=1

helm install grafana grafana/grafana \
  --namespace monitoring \
  --set persistence.enabled=true
```
