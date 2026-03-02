---
phase: 07-setup-script
plan: 01
subsystem: cli, api
tags: [click, jmap, carddav, vcard, cli]

# Dependency graph
requires:
  - phase: 06-configurable-categories
    provides: MailroomSettings with triage_categories, required_mailboxes, contact_groups
provides:
  - Click CLI framework with setup and run subcommands
  - JMAPClient.create_mailbox() for provisioning mailboxes via Mailbox/set
  - JMAPClient.session_capabilities for downstream sieve checking
  - CardDAVClient.create_group() for creating Apple-style contact group vCards
affects: [07-02, 07-03]

# Tech tracking
tech-stack:
  added: [click>=8.1]
  patterns: [Click group with invoke_without_command for backward compat, Mailbox/set JMAP pattern, Apple-style group vCard creation]

key-files:
  created: [src/mailroom/cli.py]
  modified: [pyproject.toml, src/mailroom/__main__.py, src/mailroom/clients/jmap.py, src/mailroom/clients/carddav.py, tests/test_jmap_client.py, tests/test_carddav_client.py]

key-decisions:
  - "invoke_without_command=True preserves python -m mailroom backward compat"
  - "session_capabilities stored as raw dict for flexible downstream inspection"

patterns-established:
  - "CLI dispatch: __main__.py imports cli(), run subcommand lazy-imports main()"
  - "JMAP create pattern: Mailbox/set with create map, check created/notCreated"
  - "CardDAV create pattern: PUT with If-None-Match: * and X-ADDRESSBOOKSERVER-KIND:group"

requirements-completed: [SETUP-01, SETUP-02, SETUP-06]

# Metrics
duration: 4min
completed: 2026-02-26
---

# Phase 07 Plan 01: CLI Framework and Client Create Methods Summary

**Click CLI with setup/run subcommands, JMAPClient.create_mailbox via Mailbox/set, and CardDAVClient.create_group with Apple-style vCards**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-26T14:41:58Z
- **Completed:** 2026-02-26T14:45:39Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- Click CLI group with `setup` (stub) and `run` subcommands, backward-compatible `python -m mailroom`
- JMAPClient extended with `create_mailbox(name, parent_id)` and `session_capabilities` property
- CardDAVClient extended with `create_group(name)` for Apple-style contact group vCards
- 219 total tests passing (211 existing + 8 new)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Click CLI framework and wire __main__.py** - `be602f4` (feat)
2. **Task 2: Extend JMAPClient with create_mailbox and session capabilities** - `0d6af2b` (feat)
3. **Task 3: Extend CardDAVClient with create_group** - `8502f52` (feat)

## Files Created/Modified
- `src/mailroom/cli.py` - Click CLI group with setup and run subcommands
- `pyproject.toml` - Added click dependency and mailroom console script entry point
- `src/mailroom/__main__.py` - Updated to dispatch through CLI for backward compat
- `src/mailroom/clients/jmap.py` - Added create_mailbox(), session_capabilities, downloadUrl storage
- `src/mailroom/clients/carddav.py` - Added create_group() for Apple-style contact groups
- `tests/test_jmap_client.py` - 6 new tests: create_mailbox (3), capabilities (2), empty caps (1)
- `tests/test_carddav_client.py` - 3 new tests: create_group success, not connected, HTTP error

## Decisions Made
- Used `invoke_without_command=True` on Click group to preserve backward compatibility with `python -m mailroom`
- Stored session_capabilities as raw dict (not typed) for flexible downstream inspection by sieve checking
- Followed existing test patterns: no URL matching for PUT mocks (httpx_mock catches unmatched requests)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CLI framework ready for Plan 02 to implement the setup provisioner
- create_mailbox and create_group methods ready for orchestration
- session_capabilities ready for Plan 03 sieve guidance module

---
*Phase: 07-setup-script*
*Completed: 2026-02-26*
