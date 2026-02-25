# Phase 4: Packaging and Deployment - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Wrap Mailroom into a long-lived polling service running in a Docker container on the home Kubernetes cluster. Includes the main polling loop, Dockerfile, k8s manifests (Deployment, ConfigMap, Secret template, Namespace), GitHub Actions CI for image build/push, and externalized configuration. No new triage features or workflow changes.

</domain>

<decisions>
## Implementation Decisions

### Polling loop behavior
- Fixed interval polling (configurable, default 5 minutes) — no EventSource/push
- Tiered error handling:
  - **Startup failures** (can't connect, missing config, can't resolve mailboxes) → crash immediately, let k8s restart
  - **Transient runtime errors** (single poll cycle fails) → log error, skip cycle, continue polling. Triage labels persist so work retries naturally next cycle
  - **Persistent runtime errors** (e.g., 10+ consecutive failures) → crash, something systemic is wrong
- Graceful shutdown on SIGTERM: finish processing the current poll cycle before exiting
- HTTP health endpoint (`/healthz`) for k8s liveness/readiness probes. Readiness can check recency of last successful poll

### Credential & config flow
- Plain k8s Secrets (manual `kubectl create secret` or apply from local file)
- Commit a `secret.yaml.example` with placeholder values — actual secret not in git
- All `MAILROOM_` env vars go into a ConfigMap (poll interval, mailbox names, label names, group names, log level, warnings toggle)
- Inject as env vars via `envFrom` in the Deployment spec — zero code changes needed since pydantic-settings already reads env vars

### Image build & registry
- GitHub Actions CI: push to main triggers Docker build + push
- Registry: ghcr.io (per DEPLOY-05 requirement)
- Public repository — no imagePullSecrets needed in the cluster

### Claude's Discretion
- Image tagging strategy (git SHA, latest, semver, or combination)
- Dockerfile base image and multi-stage build approach
- Exact health endpoint implementation (minimal HTTP server framework choice)
- Consecutive failure threshold for crash decision
- GitHub Actions workflow specifics (caching, build matrix, etc.)

### Cluster integration
- Dedicated `mailroom` namespace
- Minimal resource limits: ~64-128Mi memory, ~100m CPU (requests = limits)
- No monitoring/metrics endpoint — structured JSON logs to stdout are sufficient, check with `kubectl logs`
- Manual deployment via `kubectl apply -f k8s/`
- No GitOps tooling (Flux/ArgoCD)

</decisions>

<specifics>
## Specific Ideas

- User asked about JMAP EventSource (long-polling) as an alternative — decided against it for simplicity. Fixed polling is sufficient for email triage on a home service
- Error handling should follow cloud-native conventions: crash for unrecoverable, continue for transient
- K8s manifest structure should work with a single `kubectl apply -f k8s/` command

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-packaging-and-deployment*
*Context gathered: 2026-02-25*
