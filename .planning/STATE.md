# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** One label tap on a phone triages an entire sender -- all their backlogged emails move to the right place, and all future emails are auto-routed.
**Current focus:** Phase 3.1 complete -- person contact type with @ToPerson label. Ready for Phase 4.

## Current Position

Phase: 3.1 of 4 (Person Contact Type with @ToPerson Label)
Plan: 3 of 3 in current phase (PHASE COMPLETE)
Status: Phase 03.1 complete -- all plans executed, person/company contact types validated against live Fastmail
Last activity: 2026-02-25 - Plan 03.1-03 complete: human integration tests for person and company contact types

Progress: [██████████] 100% (Phase 3.1 done, Phase 4 not started)

## Performance Metrics

**Velocity:**
- Total plans completed: 13
- Average duration: 3.6 min
- Total execution time: 0.82 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-and-jmap-client | 3/3 | 8 min | 2.7 min |
| 02-carddav-client-validation-gate | 3/3 | 10 min | 3.3 min |
| 03-triage-pipeline | 3/3 | 13 min | 4.3 min |
| 03.1-person-contact-type-with-toperson-label | 3/3 | 17 min | 5.7 min |

**Recent Trend:**
- Last 5 plans: 03-02 (4 min), 03-03 (5 min), 03.1-01 (6 min), 03.1-02 (6 min), 03.1-03 (5 min)
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
- [03-01]: poll() catches all exceptions from _process_sender via except Exception for retry safety (TRIAGE-06)
- [03-01]: _apply_error_label wraps all JMAP calls in try/except to prevent transient failures from crashing poll cycle
- [03-01]: Post-query @MailroomError filtering via Email/get with mailboxIds check (single JMAP call)
- [03-01]: destination_mailbox added to label_to_group_mapping for self-contained destination routing
- [03-02]: _check_already_grouped runs during per-sender processing (not pre-mutation gate) to handle CardDAV transient failures via retry
- [03-02]: CardDAVClient.check_membership added as public method to keep protocol logic in the client (not workflow)
- [03-02]: Destination mailbox resolved via config's destination_mailbox field (Imbox->Inbox, others match group name)
- [03-02]: Empty sweep still removes triage label -- sweep query always executes per user decision
- [03-03]: _process_sender sender_names parameter optional (default None) for backward compatibility with direct callers
- [03-03]: First non-None name wins for sender_names across multiple emails from same sender
- [03-03]: Empty/whitespace name normalization to None at JMAP extraction layer (not workflow)
- [03.1-01]: Company vCard uses empty vobject.vcard.Name() for N:;;;; and ORG as list per vCard 3.0 spec
- [03.1-01]: Person vCard uses nameparser.HumanName for first/last parsing; single-word names get given-only
- [03.1-01]: NOTE append: existing contacts get "\n\nUpdated by Mailroom on {date}" appended, never overwrite
- [03.1-01]: name_mismatch: case-insensitive stripped FN comparison, False for new contacts or None display_name
- [03.1-01]: required_mailboxes property centralizes startup mailbox validation with conditional @MailroomWarning
- [03.1-02]: _apply_warning_label follows same pattern as _apply_error_label (per-email Email/set, non-blocking try/except)
- [03.1-02]: Warning applied only to triggering email_ids, not swept sender emails
- [03.1-02]: name_mismatch check uses result.get("name_mismatch", False) for backward safety
- [03.1-03]: Human tests follow existing standalone pattern (own connections, dotenv, step-level PASS/FAIL)
- [03.1-03]: Visual verification pauses included for Fastmail UI contact rendering confirmation

### Pending Todos

None yet.

### Roadmap Evolution

- Phase 03.1 inserted after Phase 03: Person Contact Type with @ToPerson Label (URGENT)

### Blockers/Concerns

- ~~[Phase 2]: CardDAV KIND:group contact model is from training data, not live-verified.~~ RESOLVED: Validated against live Fastmail on 2026-02-24. All operations confirmed working.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Commit human tests, gitignore, and dependency changes from phase verification | 2026-02-24 | 118cfc1 | [1-commit-human-tests-gitignore-and-depende](./quick/1-commit-human-tests-gitignore-and-depende/) |

## Session Continuity

Last session: 2026-02-25
Stopped at: Completed 03.1-03-PLAN.md (Phase 3.1 complete)
Resume file: None
