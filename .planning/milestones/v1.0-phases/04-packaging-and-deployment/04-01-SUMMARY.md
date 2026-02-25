---
phase: 04-packaging-and-deployment
plan: 01
subsystem: infra
tags: [docker, uv, polling-loop, health-endpoint, signal-handling, structlog]

# Dependency graph
requires:
  - phase: 03.1-person-contact-type-with-toperson-label
    provides: Complete ScreenerWorkflow.poll() with all contact types
provides:
  - "python -m mailroom entry point with polling loop, signal handling, health endpoint"
  - "Multi-stage Dockerfile with uv for slim Python image"
  - ".dockerignore excluding dev/test/planning files"
affects: [04-02, 04-03]

# Tech tracking
tech-stack:
  added: [http.server, threading, signal]
  patterns: [threading.Event for graceful shutdown, daemon thread health server, tiered error handling]

key-files:
  created: [src/mailroom/__main__.py, Dockerfile, .dockerignore]
  modified: []

key-decisions:
  - "stdlib http.server on daemon thread for /healthz (zero external deps)"
  - "threading.Event.wait() instead of time.sleep() for immediate SIGTERM wake"
  - "10 consecutive failures threshold for persistent crash"
  - "Health returns 200 before first poll (just-started grace)"

patterns-established:
  - "Polling loop: threading.Event for shutdown signal, Event.wait for interruptible sleep"
  - "Health endpoint: class-level attributes for shared state between threads"
  - "Startup crash: let pydantic/httpx/ValueError propagate naturally, no try/except"

requirements-completed: [DEPLOY-01]

# Metrics
duration: 2min
completed: 2026-02-25
---

# Phase 4 Plan 1: Entry Point and Docker Summary

**Polling service entry point with SIGTERM graceful shutdown, /healthz health endpoint on daemon thread, tiered error handling, and multi-stage uv Docker image**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-25T02:55:58Z
- **Completed:** 2026-02-25T02:58:08Z
- **Tasks:** 2
- **Files created:** 3

## Accomplishments
- Polling loop entry point (`python -m mailroom`) with full startup sequence and shutdown handling
- Health endpoint on daemon thread (port 8080) with staleness detection for k8s probes
- Multi-stage Dockerfile using uv for fast builds, non-root runtime user, ~229MB final image
- .dockerignore excluding all non-build files from Docker context

## Task Commits

Each task was committed atomically:

1. **Task 1: Create __main__.py polling loop with health endpoint and signal handling** - `4cdd331` (feat)
2. **Task 2: Create Dockerfile and .dockerignore for multi-stage uv build** - `e920d94` (feat)

## Files Created/Modified
- `src/mailroom/__main__.py` - Polling service entry point with signal handling, health endpoint, tiered error handling (148 lines)
- `Dockerfile` - Multi-stage build with uv builder and slim runtime with non-root user (35 lines)
- `.dockerignore` - Excludes dev files, tests, planning, git from build context (17 lines)

## Decisions Made
- Used stdlib http.server.ThreadingHTTPServer for /healthz endpoint (zero external dependencies, sufficient for k8s probes)
- threading.Event.wait() for interruptible sleep (wakes immediately on SIGTERM, unlike time.sleep)
- 10 consecutive failures threshold for persistent crash (50 min at 5-min intervals)
- Health endpoint returns 200 before first poll completes (just-started grace period)
- Signal handler only sets event flag -- cooperative shutdown, no cleanup in handler

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Entry point and Docker image ready for k8s manifests (Plan 02)
- Docker image builds and runs `python -m mailroom` as CMD
- Health endpoint on port 8080 ready for liveness/readiness probes
- ConfigMap/Secret env var injection will work via existing pydantic-settings MAILROOM_ prefix

## Self-Check: PASSED

All files verified present, all commits verified in git log.

---
*Phase: 04-packaging-and-deployment*
*Completed: 2026-02-25*
