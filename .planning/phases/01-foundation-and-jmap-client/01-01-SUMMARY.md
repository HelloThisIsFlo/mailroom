---
phase: 01-foundation-and-jmap-client
plan: 01
subsystem: infra
tags: [python, uv, pydantic-settings, structlog, pytest, ruff]

# Dependency graph
requires: []
provides:
  - "Python project scaffold with src/ layout and uv dependency management"
  - "MailroomSettings config class with MAILROOM_ env prefix and typed defaults"
  - "configure_logging() for JSON (prod) and console (dev) structured output"
  - "Test infrastructure with pytest, conftest.py, 10 passing tests"
affects: [01-02, 01-03, 02-carddav-contacts, 03-triage-workflow, 04-main-loop]

# Tech tracking
tech-stack:
  added: [httpx, pydantic-settings, structlog, ruff, pytest, pytest-httpx]
  patterns: [pydantic-settings-env-prefix, structlog-json-console-switch, src-layout]

key-files:
  created:
    - pyproject.toml
    - src/mailroom/__init__.py
    - src/mailroom/core/__init__.py
    - src/mailroom/core/config.py
    - src/mailroom/core/logging.py
    - src/mailroom/clients/__init__.py
    - src/mailroom/workflows/__init__.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_config.py
    - tests/test_logging.py
  modified: []

key-decisions:
  - "Individual env vars for label/group config (not structured/nested) -- maps cleanly to k8s ConfigMap entries"
  - "PrintLoggerFactory writes to stderr (not stdout) for proper Docker/k8s log collection"
  - "cache_logger_on_first_use=False for testability (allows reconfiguring in tests)"
  - "carddav_password with empty default for Phase 1 forward compat (not required until Phase 2)"

patterns-established:
  - "Config pattern: pydantic-settings with MAILROOM_ prefix, required fields have no defaults"
  - "Logging pattern: structlog with TTY detection for dev/prod mode switching"
  - "Test pattern: monkeypatch.setenv for config tests, StringIO stderr capture for log tests"
  - "Project layout: src/mailroom/{core,clients,workflows}/ with tests/ at root"

requirements-completed: [CONF-01, CONF-02, CONF-03, LOG-01, LOG-02]

# Metrics
duration: 3min
completed: 2026-02-24
---

# Phase 1 Plan 1: Project Scaffold, Config, and Logging Summary

**Python project with uv, pydantic-settings config (MAILROOM_ env prefix, typed defaults), and structlog JSON/console logging -- 10 tests passing**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-24T00:59:23Z
- **Completed:** 2026-02-24T01:02:34Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- Python project scaffolded with uv (src/ layout, Python 3.12, all dependencies installed)
- MailroomSettings config class loads all settings from MAILROOM_-prefixed env vars with sensible defaults matching user's Fastmail setup
- Structured logging with JSON output in prod (non-TTY) and colored console in dev (TTY), with level filtering and exception serialization
- 10 tests passing across config (5) and logging (5) modules

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold Python project with uv and install dependencies** - `d9cdcb4` (feat)
2. **Task 2: Implement configuration module with pydantic-settings** - `5b4434c` (feat)
3. **Task 3: Implement structured logging module with structlog** - `04888e0` (feat)
4. **Lint fix: import sorting in test_config.py** - `2cd7ce4` (chore)

## Files Created/Modified
- `pyproject.toml` - Project metadata, dependencies (httpx, pydantic-settings, structlog), dev deps (ruff, pytest, pytest-httpx), ruff + pytest config
- `.python-version` - Python 3.12
- `src/mailroom/__init__.py` - Package root
- `src/mailroom/core/config.py` - MailroomSettings with MAILROOM_ prefix, triage_labels and label_to_group_mapping properties
- `src/mailroom/core/logging.py` - configure_logging() for JSON/console output, get_logger() convenience
- `src/mailroom/clients/__init__.py` - Placeholder for JMAP/CardDAV clients
- `src/mailroom/workflows/__init__.py` - Placeholder for triage workflows
- `tests/conftest.py` - Shared test fixtures (empty for now)
- `tests/test_config.py` - 5 tests: defaults, required fields, env overrides, triage_labels, label_to_group_mapping
- `tests/test_logging.py` - 5 tests: JSON output, level filtering, bound context, exception logging, get_logger

## Decisions Made
- **Individual env vars for label/group config:** Each label and group is a separate MAILROOM_ env var (e.g., MAILROOM_LABEL_TO_IMBOX). Maps directly to k8s ConfigMap entries without needing structured/nested parsing.
- **Logs to stderr:** PrintLoggerFactory configured with `file=sys.stderr` for proper Docker/k8s log collection (stdout is for application output).
- **cache_logger_on_first_use=False:** Allows tests to reconfigure structlog between test cases without stale cached loggers.
- **Forward-compat carddav_password:** Added with empty string default so the field exists for Phase 2 without requiring it in Phase 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff import sorting in test_config.py**
- **Found during:** Final verification (ruff check)
- **Issue:** Import block in test_config.py had a blank line between stdlib and third-party imports that ruff's isort rules flagged
- **Fix:** Ran `ruff check --fix` to auto-sort imports
- **Files modified:** tests/test_config.py
- **Verification:** `ruff check src/ tests/` passes clean
- **Committed in:** 2cd7ce4

---

**Total deviations:** 1 auto-fixed (1 bug/lint)
**Impact on plan:** Trivial import ordering fix. No scope creep.

## Issues Encountered
- structlog's PrintLoggerFactory defaults to stdout, not stderr. Tests initially captured stderr and found empty output. Fixed by configuring `PrintLoggerFactory(file=sys.stderr)` and using `patch.object(sys, "stderr", buf)` with `buf.isatty = lambda: False` in tests.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Project foundation complete: dependencies installed, config loading from env vars, structured logging operational
- Ready for Plan 02 (JMAP client) -- httpx installed, module structure in place at clients/
- All 10 tests passing, ruff clean, `import mailroom` works

## Self-Check: PASSED

All 13 files verified present. All 4 commit hashes verified in git log.

---
*Phase: 01-foundation-and-jmap-client*
*Completed: 2026-02-24*
