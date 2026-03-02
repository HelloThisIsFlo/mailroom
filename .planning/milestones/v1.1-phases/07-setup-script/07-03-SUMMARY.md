---
phase: 07-setup-script
plan: 03
subsystem: cli, setup
tags: [sieve-guidance, fastmail-ui, routing-rules, human-tests, idempotency]

# Dependency graph
requires:
  - phase: 07-setup-script-02
    provides: Provisioner with run_setup(), plan_resources(), apply_resources(), print_plan()
provides:
  - Sieve rule guidance module generating instructions for all configured root categories
  - Default mode with sieve-style snippets (contact group conditions + folder actions)
  - UI guide mode with Fastmail Settings step-by-step instructions
  - Screener catch-all rule guidance in both modes
  - Human test for setup dry-run (test_14) validating output format and no-change guarantee
  - Human test for setup apply + idempotency (test_15) validating resource creation
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [Guidance-only sieve module (no introspection), Root category filtering via parent=None check]

key-files:
  created: [src/mailroom/setup/sieve_guidance.py, tests/test_sieve_guidance.py, human-tests/test_14_setup_dry_run.py, human-tests/test_15_setup_apply.py]
  modified: [src/mailroom/setup/provisioner.py]

key-decisions:
  - "Guidance-only sieve module -- no sieve introspection, no SieveScript/get, no capability checking. Future milestone handles programmatic rule creation."
  - "Child categories (e.g., Person) skipped in guidance output -- they inherit routing from parent category (Imbox)"
  - "Sieve reference snippets are informational only with low confidence on exact jmapquery JSON format"

patterns-established:
  - "Root category filtering: [cat for cat in _resolved_categories if cat.parent is None]"
  - "Guidance module returns string (no printing) -- caller decides output mechanism"

requirements-completed: [SETUP-03, SETUP-04, SETUP-05]

# Metrics
duration: 3min
completed: 2026-02-26
---

# Phase 07 Plan 03: Sieve Guidance and Human Tests Summary

**Sieve rule guidance module with default sieve-snippet and Fastmail UI modes, plus human integration tests for setup dry-run and apply+idempotency flows**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T14:53:59Z
- **Completed:** 2026-02-26T14:57:18Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Sieve guidance module generating human-readable routing rule instructions for all root categories (skipping children)
- Two output modes: default sieve-style snippets with jmapquery references, and --ui-guide Fastmail Settings step-by-step
- Provisioner integration prints guidance after resource plan/apply in both dry-run and apply modes
- 245 total tests passing (229 existing + 16 new sieve guidance tests)
- Two human integration tests: test_14 (dry-run verification) and test_15 (apply + idempotency)

## Task Commits

Each task was committed atomically:

1. **Task 1: Build sieve guidance module and integrate into provisioner** - `7128690` (feat)
2. **Task 2: Create human integration tests for setup dry-run and apply** - `3605326` (feat)

## Files Created/Modified
- `src/mailroom/setup/sieve_guidance.py` - generate_sieve_guidance() with default and UI guide modes
- `src/mailroom/setup/provisioner.py` - Added sieve guidance output after resource plan/apply
- `tests/test_sieve_guidance.py` - 16 unit tests: default mode (8), UI guide mode (5), custom categories (3)
- `human-tests/test_14_setup_dry_run.py` - Validates dry-run output, sieve guidance, no-change guarantee
- `human-tests/test_15_setup_apply.py` - Validates apply resource creation, sieve guidance, idempotent re-run

## Decisions Made
- Guidance-only approach: no sieve introspection, no SieveScript/get API calls, no capability checking. Outputs instructions for ALL categories unconditionally. Programmatic sieve rule creation deferred to future milestone.
- Child categories (Person) filtered out by checking parent is None -- they inherit routing from their parent category and don't need separate rules.
- Sieve reference snippets included as informational comments (low confidence on exact jmapquery JSON format) alongside clear UI instructions.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 07 (Setup Script) fully complete: CLI framework, provisioner, sieve guidance, human tests
- Complete setup flow: `mailroom setup` (dry-run) and `mailroom setup --apply` with routing rule guidance
- Ready for Phase 08 (EventSource Push) which is the final v1.1 phase

---
*Phase: 07-setup-script*
*Completed: 2026-02-26*
