---
phase: 11-config-layer
plan: 04
subsystem: config
tags: [pydantic, validation, sieve, cli, click]

# Dependency graph
requires:
  - phase: 11-config-layer (plans 01-03)
    provides: CFG-02 Inbox rejection, sieve guidance with ui_guide mode
provides:
  - Case-insensitive CFG-02 Inbox rejection (inbox, INBOX, Inbox all caught)
  - Clean ValidationError handling in __main__.py
  - Simplified sieve guidance without ui_guide mode or commented sieve blocks
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Case-insensitive string validation via .lower() comparison"
    - "Pydantic ValidationError catch at entry point for clean user-facing errors"

key-files:
  created: []
  modified:
    - src/mailroom/core/config.py
    - src/mailroom/__main__.py
    - src/mailroom/cli.py
    - src/mailroom/setup/provisioner.py
    - src/mailroom/setup/sieve_guidance.py
    - tests/test_config.py
    - tests/test_sieve_guidance.py
    - human-tests/test_14_setup_dry_run.py
    - human-tests/test_15_setup_apply.py

key-decisions:
  - "Case-insensitive Inbox check uses resolved_mailbox.lower() == 'inbox' (single comparison point)"
  - "Kept informational jmapquery mention in sieve guidance intro (explains why UI creation is needed)"

patterns-established: []

requirements-completed: [CFG-02, CFG-08]

# Metrics
duration: 4min
completed: 2026-03-03
---

# Phase 11 Plan 04: Gap Closure Summary

**Case-insensitive CFG-02 Inbox rejection for all case variants, clean ValidationError output, and removal of dead ui_guide code and commented sieve blocks**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-03T15:25:08Z
- **Completed:** 2026-03-03T15:29:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- CFG-02 now rejects destination_mailbox set to "inbox", "INBOX", "Inbox", or any case variant with the same helpful error
- __main__.py catches ValidationError and prints a clean one-line message instead of raw Pydantic traceback
- Removed --ui-guide CLI flag, ui_guide parameter from all functions, and entire _build_ui_guide() function
- Removed commented sieve equivalent blocks (fileinto/jmapquery) from sieve guidance output
- Deleted 8 tests (UI guide mode class + sieve reference test), net reduction of ~150 lines of dead code

## Task Commits

Each task was committed atomically:

1. **Task 1: CFG-02 case-insensitive Inbox rejection (TDD RED)** - `43c7019` (test)
2. **Task 1: CFG-02 case-insensitive Inbox rejection (TDD GREEN)** - `f7669c8` (feat)
3. **Task 2: Remove --ui-guide flag and commented sieve blocks** - `be7a3b4` (feat)

## Files Created/Modified
- `src/mailroom/core/config.py` - Case-insensitive CFG-02 check via .lower()
- `src/mailroom/__main__.py` - ValidationError catch with clean stderr output
- `src/mailroom/cli.py` - Removed --ui-guide option from setup command
- `src/mailroom/setup/provisioner.py` - Removed ui_guide parameter from run_setup()
- `src/mailroom/setup/sieve_guidance.py` - Removed ui_guide parameter, _build_ui_guide(), and commented sieve blocks
- `tests/test_config.py` - Added 3 case-insensitive Inbox rejection tests
- `tests/test_sieve_guidance.py` - Deleted UI guide test class and sieve reference test, updated all call signatures
- `human-tests/test_14_setup_dry_run.py` - Updated run_setup() call to match new signature
- `human-tests/test_15_setup_apply.py` - Updated run_setup() calls to match new signature

## Decisions Made
- Case-insensitive Inbox check uses `resolved_mailbox.lower() == "inbox"` at the single validation point in `_validate_categories` -- no need for regex or multiple comparisons
- Kept the informational line in sieve guidance intro that explains Fastmail uses jmapquery internally (this is explanatory context, not a commented sieve block)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Additional ui_guide references in TestSyntaxHighlighting**
- **Found during:** Task 2 (removing ui_guide references)
- **Issue:** The `replace_all` for `ui_guide=False` missed calls in TestSyntaxHighlighting that used `tty_settings` instead of `settings`
- **Fix:** Applied additional replacement for `generate_sieve_guidance(tty_settings, ui_guide=False)` calls
- **Files modified:** tests/test_sieve_guidance.py
- **Verification:** All 313 tests pass
- **Committed in:** be7a3b4 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Straightforward fix, same intent as plan. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 11 gap closure complete -- all UAT issues resolved
- Ready for Phase 12 (Workflow Runtime)

---
*Phase: 11-config-layer*
*Completed: 2026-03-03*
