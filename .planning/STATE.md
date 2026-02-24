# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** One label tap on a phone triages an entire sender -- all their backlogged emails move to the right place, and all future emails are auto-routed.
**Current focus:** Phase 2 complete. Ready for Phase 3: Triage Pipeline

## Current Position

Phase: 2 of 4 (CardDAV Client Validation Gate) -- COMPLETE
Plan: 3 of 3 in current phase (all complete)
Status: Phase complete -- validation gate passed, all CardDAV operations verified against live Fastmail
Last activity: 2026-02-24 - Phase 2 validation gate PASSED: all human test scripts confirmed against live Fastmail

Progress: [███████░░░] 70%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: 2.7 min
- Total execution time: 0.31 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-and-jmap-client | 3/3 | 8 min | 2.7 min |
| 02-carddav-client-validation-gate | 3/3 | 10 min | 3.3 min |

**Recent Trend:**
- Last 5 plans: 01-03 (3 min), 02-01 (3 min), 02-02 (4 min), 02-03 (3 min)
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: CardDAV is a validation gate (Phase 2) -- do not build triage pipeline until KIND:group model is verified against live Fastmail
- [Roadmap]: Main loop and deployment merged into single phase (Phase 4) -- polling loop is trivial, belongs with packaging
- [01-01]: Individual env vars for label/group config (not structured) -- maps cleanly to k8s ConfigMap entries
- [01-01]: PrintLoggerFactory writes to stderr for proper Docker/k8s log collection
- [01-01]: cache_logger_on_first_use=False for testability
- [01-01]: carddav_password with empty default for Phase 1 forward compat
- [01-02]: Inbox resolved by role='inbox' (not name) to avoid parent/child name collisions
- [01-02]: Custom mailboxes prefer top-level (parentId=None) for duplicate name disambiguation
- [01-02]: RuntimeError with 'not connected' message for pre-connect access guards
- [01-03]: query_emails() combines JMAP-03 and JMAP-06 via optional sender parameter (not separate methods)
- [01-03]: batch_move_emails() is generic -- Imbox/Inbox special case is caller responsibility (passes inbox_id in add_mailbox_ids)
- [01-03]: Batch chunking at 100 emails per Email/set call (conservative under 500 minimum maxObjectsInSet)
- [02-01]: REPORT addressbook-query with no filter for single-round-trip group fetch
- [02-01]: card.contents dict access for vobject X-properties (more reliable than attribute access)
- [02-01]: Full absolute URLs in _addressbook_url for simpler downstream usage
- [02-02]: ElementTree for REPORT XML body construction (proper escaping of email special chars)
- [02-02]: First-match strategy for duplicate contacts during upsert (deterministic behavior)
- [02-02]: Merge-cautious: only fill empty fields, never overwrite existing data
- [02-02]: add_to_group is idempotent (skips PUT when contact already a member)
- [02-03]: ETag conflict test uses external edit (user edits group in Fastmail) for deterministic testing
- [02-03]: Each human test script is standalone with own connection/validation
- [02-03]: Manual cleanup after tests to allow visual Fastmail verification first
- [02-03]: Discovery URL fixed from / to /.well-known/carddav for proper CardDAV discovery
- [02-03]: Logging deferred to uniform approach in later phase (added then reverted per user preference)

### Pending Todos

None yet.

### Blockers/Concerns

- ~~[Phase 2]: CardDAV KIND:group contact model is from training data, not live-verified.~~ RESOLVED: Validated against live Fastmail on 2026-02-24. All operations confirmed working.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Commit human tests, gitignore, and dependency changes from phase verification | 2026-02-24 | 118cfc1 | [1-commit-human-tests-gitignore-and-depende](./quick/1-commit-human-tests-gitignore-and-depende/) |

## Session Continuity

Last session: 2026-02-24
Stopped at: Completed 02-03-PLAN.md -- Phase 2 validation gate passed
Resume file: None
