---
phase: quick-6
plan: 01
subsystem: infra
tags: [helm, kubernetes, deployment, security]

# Dependency graph
requires:
  - phase: 09.1.1-helm-chart-migration
    provides: Helm chart with PodSecurity hardening
provides:
  - Simplified Helm chart with vanilla textbook patterns only
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Vanilla Helm chart: no securityContext, no namespace management -- keep infra concerns out of app charts"

key-files:
  created: []
  modified:
    - helm/mailroom/templates/deployment.yaml
    - helm/mailroom/templates/setup-job.yaml
    - helm/mailroom/templates/_helpers.tpl

key-decisions:
  - "Namespace management removed entirely -- external concern, not app chart responsibility"
  - "Security hardening removed -- PodSecurity Admission is cluster-level, not app-level"

patterns-established:
  - "Helm chart contains only vanilla textbook patterns: Deployment, Job, ConfigMap, Secret, _helpers.tpl with standard name/labels helpers"

requirements-completed: [TODO-15]

# Metrics
duration: 1min
completed: 2026-03-02
---

# Quick Task 6: Simplify Helm Chart Summary

**Stripped PodSecurity securityContext, namespace.yaml, and readOnlyRootFilesystem /tmp hack from Helm chart -- only vanilla textbook patterns remain**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-02T12:26:04Z
- **Completed:** 2026-03-02T12:27:35Z
- **Tasks:** 2
- **Files modified:** 4 (3 modified, 1 deleted)

## Accomplishments
- Deleted namespace.yaml template (namespaces managed externally, not by app charts)
- Removed podSecurityContext and containerSecurityContext template definitions from _helpers.tpl
- Stripped all securityContext blocks and /tmp emptyDir hack from deployment.yaml and setup-job.yaml
- Validated chart renders clean YAML via `helm template` with all expected resources and zero security cruft

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove security hardening and namespace template** - `dad4f0c` (chore)
2. **Task 2: Validate chart renders correctly** - no commit (validation-only, no file changes)

## Files Created/Modified
- `helm/mailroom/templates/namespace.yaml` - Deleted (namespace management removed)
- `helm/mailroom/templates/_helpers.tpl` - Removed podSecurityContext and containerSecurityContext template definitions
- `helm/mailroom/templates/deployment.yaml` - Removed pod/container securityContext blocks, /tmp volumeMount, tmp emptyDir volume
- `helm/mailroom/templates/setup-job.yaml` - Same removals as deployment.yaml

## Decisions Made
- Namespace management is an external concern -- app charts should not create/manage namespaces
- PodSecurity Admission securityContext is cluster/namespace policy, not app chart responsibility
- readOnlyRootFilesystem + /tmp emptyDir is an infrastructure hack that adds complexity without app-level value

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Steps
- Chart is simplified and ready for standard Helm usage
- Security policies should be enforced at namespace/cluster level if needed

---
*Quick Task: 6-simplify-helm-chart-to-vanilla-textbook*
*Completed: 2026-03-02*
