---
phase: quick-6
plan: 01
subsystem: infra
tags: [helm, kubernetes, namespace, pss, kubectl]

requires:
  - phase: 09.1.1-helm-chart-migration
    provides: Helm chart with namespace.yaml template and deploy.sh script
provides:
  - Conflict-free Helm deployments via kubectl pre-flight namespace creation
  - Idempotent PSS labeling independent of Helm ownership
affects: [deployment, helm]

tech-stack:
  added: []
  patterns:
    - "Pre-flight kubectl for resources Helm shouldn't own"
    - "Idempotent create via --dry-run=client -o yaml | kubectl apply"

key-files:
  created: []
  modified:
    - scripts/deploy.sh
  deleted:
    - helm/mailroom/templates/namespace.yaml

key-decisions:
  - "Namespace ownership moved to kubectl (not Helm) to avoid annotation conflicts on existing namespaces"
  - "DRY_RUN flag gates kubectl commands separately from Helm --dry-run"

patterns-established:
  - "Pre-flight kubectl pattern: create cluster-scoped resources before Helm runs"

requirements-completed: [QUICK-6]

duration: 1min
completed: 2026-03-02
---

# Quick Task 6: Fix Helm Namespace Ownership Conflict Summary

**Removed namespace.yaml from Helm chart, added idempotent kubectl pre-flight namespace creation with PSS labels to deploy.sh**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-02T01:11:38Z
- **Completed:** 2026-03-02T01:12:21Z
- **Tasks:** 1
- **Files modified:** 2 (1 deleted, 1 modified)

## Accomplishments
- Eliminated Helm ownership conflict by removing namespace.yaml from chart templates
- Added idempotent kubectl namespace creation with all 6 PSS labels to deploy.sh
- Dry-run mode properly gates kubectl commands (echo-only, no side effects)
- Retained --create-namespace on helm command as safety net

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove namespace.yaml and add pre-flight namespace creation to deploy.sh** - `80e34fc` (fix)

## Files Created/Modified
- `helm/mailroom/templates/namespace.yaml` - DELETED (was causing Helm ownership conflicts)
- `scripts/deploy.sh` - Added pre-flight kubectl namespace creation with PSS labels, DRY_RUN flag

## Decisions Made
- Namespace ownership moved to kubectl instead of Helm to avoid annotation conflicts when namespace pre-exists
- Separate DRY_RUN boolean tracks script dry-run mode independently from Helm's --dry-run flag in EXTRA_ARGS

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Steps
- Deploy with `scripts/deploy.sh` to verify namespace creation works on cluster
- Both fresh installs and upgrades should succeed without ownership conflicts

---
*Quick Task: 6-fix-helm-namespace-ownership-conflict*
*Completed: 2026-03-02*
