---
phase: quick-4
plan: 01
subsystem: tooling
tags: [jmap, sse, eventsource, fastmail, push-notifications, discovery]

# Dependency graph
requires:
  - phase: 01-foundation-and-jmap-client
    provides: JMAPClient with session discovery and httpx
provides:
  - "JMAP EventSource SSE discovery script (human-tests/test_14_eventsource.py)"
  - "EventSource research document with push architecture analysis (.research/jmap-eventsource.md)"
affects: [replace-polling-with-eventsource, push-architecture]

# Tech tracking
tech-stack:
  added: []
  patterns: [SSE manual parsing without third-party library, Fastmail envelope format handling]

key-files:
  created:
    - human-tests/test_14_eventsource.py
    - .research/jmap-eventsource.md
  modified: []

key-decisions:
  - "Manual SSE parsing instead of third-party library (simple format, no new dependency)"
  - "Fastmail wraps RFC 8620 data in envelope with 'changed' and 'type' keys -- script handles both formats"
  - "Hybrid push+poll approach recommended in research doc for reliability"

patterns-established:
  - "SSE stream parsing: accumulate lines until empty line, parse event/data/comment prefixes"
  - "Discovery scripts: connect, observe, log structured output for research"

requirements-completed: [TODO-3, TODO-4]

# Metrics
duration: 6min
completed: 2026-02-25
---

# Quick Task 4: Create JMAP EventSource Discovery Script Summary

**JMAP EventSource SSE discovery script with manual parsing and research document analyzing push architecture implications for Mailroom**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-25T19:07:42Z
- **Completed:** 2026-02-25T19:13:44Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- Standalone EventSource discovery script that connects to Fastmail's SSE endpoint and logs real-time state change events
- Manual SSE parsing handles Fastmail's envelope format (changed/type wrapper around RFC 8620 data)
- Research document capturing RFC 8620 spec details, Fastmail observations, push architecture design, debounce strategy, and hybrid approach recommendation
- Script verified against live Fastmail account: receives initial connect event with Email, Mailbox, Thread, ContactCard, AddressBook, and EmailDelivery states

## Task Commits

Each task was committed atomically:

1. **Task 1: Create JMAP EventSource discovery script** - `cf04231` (feat)
2. **Task 2: Write EventSource research document** - `c761cf2` (docs)

## Files Created
- `human-tests/test_14_eventsource.py` - Standalone SSE discovery script with --duration flag, structured event logging, and PASS/FAIL summary
- `.research/jmap-eventsource.md` - Research document with RFC 8620 spec, Fastmail observations, push architecture analysis, debounce strategy, and open questions

## Decisions Made
- **Manual SSE parsing:** Used simple line-based parsing instead of adding a third-party SSE library. The SSE format is straightforward (event:/data:/comment lines with empty-line delimiters) and httpx streaming handles it natively.
- **Fastmail envelope handling:** Discovered that Fastmail wraps RFC 8620 state data in `{"changed": {...}, "type": "connect|change"}` envelope. Script handles both this format and the raw RFC format for robustness.
- **Hybrid push+poll recommendation:** Research document recommends EventSource as primary trigger with polling fallback for reliability, based on RFC behavior and practical considerations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Fastmail SSE envelope format parsing**
- **Found during:** Task 1 (verification)
- **Issue:** Initial implementation treated all top-level data keys as account IDs, but Fastmail wraps data in `{"changed": {...}, "type": "..."}` envelope
- **Fix:** Added envelope detection in `print_state_event()` -- extracts `changed` dict for account states, displays `type` field as event subtype
- **Files modified:** `human-tests/test_14_eventsource.py`
- **Verification:** Re-ran script, confirmed proper display of account/type/state hierarchy
- **Committed in:** cf04231 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential for correct output formatting. No scope creep.

## Issues Encountered
- Script duration exceeds `--duration` flag value because SSE `iter_lines()` blocks between events (30-second ping interval means up to 30s additional wait). This is inherent to the SSE protocol -- the script correctly exits at the next line boundary after duration expires.

## User Setup Required

None - uses existing MAILROOM_JMAP_TOKEN from `.env` (same as all human tests).

## Next Steps
- Run `python human-tests/test_14_eventsource.py --duration 120` while performing Fastmail actions to populate empirical observation sections in `.research/jmap-eventsource.md`
- Use findings to inform push architecture design (TODO-4: replace polling with EventSource push and debouncer)

---
*Quick Task: 4-create-jmap-eventsource-discovery-script*
*Completed: 2026-02-25*
