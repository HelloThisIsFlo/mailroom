---
phase: 04-packaging-and-deployment
plan: 02
subsystem: infra
tags: [kubernetes, k8s, ghcr, github-actions, docker, ci]

# Dependency graph
requires:
  - phase: 04-01
    provides: Dockerfile for building the container image
provides:
  - Kubernetes manifests (namespace, configmap, secret template, deployment)
  - GitHub Actions CI workflow for Docker build + push to ghcr.io
  - .gitignore protection for k8s secrets
affects: [04-03]

# Tech tracking
tech-stack:
  added: [kubernetes, github-actions, ghcr.io]
  patterns: [envFrom config/secret injection, SHA+latest image tagging, GHA layer caching]

key-files:
  created:
    - k8s/namespace.yaml
    - k8s/configmap.yaml
    - k8s/secret.yaml.example
    - k8s/deployment.yaml
    - .github/workflows/build.yaml
  modified:
    - .gitignore

key-decisions:
  - "All ConfigMap keys use exact MAILROOM_ prefixed names matching pydantic-settings env var loading"
  - "Secret template uses stringData for human-readable placeholders with copy-fill-apply workflow"
  - "SHA + latest image tagging (no semver for personal service)"
  - "GHA layer caching for faster builds"

patterns-established:
  - "envFrom pattern: ConfigMap for non-secret config, Secret for credentials, both injected via envFrom"
  - "Secret template pattern: .example file in git, real secret in .gitignore"
  - "Health probe pattern: /healthz endpoint on port 8080 for liveness and readiness"

requirements-completed: [DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05]

# Metrics
duration: 2min
completed: 2026-02-25
---

# Phase 04 Plan 02: K8s Manifests and CI Summary

**Kubernetes deployment package with namespace, configmap, secret template, deployment with /healthz probes, and GitHub Actions CI pushing to ghcr.io**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-25T02:56:06Z
- **Completed:** 2026-02-25T02:57:42Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Complete k8s deployment package: namespace, configmap with all 15 MAILROOM_ env vars, secret template with placeholders, deployment with envFrom injection
- Deployment includes liveness/readiness probes on /healthz, resource requests (64Mi/100m) and limits (128Mi/100m), 60s termination grace period
- GitHub Actions CI workflow builds and pushes Docker images to ghcr.io on push to main with SHA + latest tagging and GHA layer caching
- .gitignore updated to prevent accidental credential commits

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Kubernetes manifests** - `19e5175` (feat)
2. **Task 2: Create GitHub Actions CI workflow and update .gitignore** - `5bd40a5` (feat)

## Files Created/Modified
- `k8s/namespace.yaml` - Dedicated mailroom namespace
- `k8s/configmap.yaml` - All 15 MAILROOM_ config env vars matching pydantic-settings fields
- `k8s/secret.yaml.example` - Template with placeholder credential values (copy to secret.yaml, fill, apply)
- `k8s/deployment.yaml` - 1-replica Deployment with envFrom, /healthz probes, resource limits
- `.github/workflows/build.yaml` - CI workflow for Docker build + push to ghcr.io
- `.gitignore` - Added k8s/secret.yaml exclusion

## Decisions Made
- All ConfigMap keys use exact MAILROOM_-prefixed uppercase names (envFrom injects them verbatim, matching pydantic-settings case_sensitive=False)
- Secret template uses stringData for human-readable placeholders rather than base64 data
- SHA + latest image tagging strategy (commit traceability + convenience, no semver for personal service)
- GHA layer caching (type=gha with mode=max) for faster subsequent builds

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. When deploying to a real cluster, copy `k8s/secret.yaml.example` to `k8s/secret.yaml`, fill in real credentials, and apply.

## Next Phase Readiness
- K8s manifests and CI pipeline ready
- Next plan (04-03) can build the main loop and health endpoint that the deployment expects on port 8080 /healthz

## Self-Check: PASSED

All 5 created files verified on disk. Both task commits (19e5175, 5bd40a5) verified in git log.

---
*Phase: 04-packaging-and-deployment*
*Completed: 2026-02-25*
