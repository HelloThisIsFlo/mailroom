# Phase 2: CardDAV Client (Validation Gate) - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

A verified CardDAV client that can manage contacts and group membership against live Fastmail. The service can search, create, and update contacts via CardDAV, and reliably assign contacts to Fastmail contact groups using the KIND:group model. This is a validation gate — the model must be proven before the triage pipeline (Phase 3) is built on top of it.

Fastmail rules that route emails based on contact group membership are a manual prerequisite, not managed by the application.

</domain>

<decisions>
## Implementation Decisions

### Contact content
- Extract display name from email headers (e.g., "Jane Smith" from "Jane Smith <jane@example.com>"); fall back to email prefix if no display name present
- Include a NOTE field: "Added by Mailroom on YYYY-MM-DD" to distinguish auto-created contacts from manual ones
- Known limitation (v1): shared-sender addresses (e.g., noreply@dpd.com) may get the wrong display name from the first triaged email. Routing still works correctly — name is cosmetic

### Existing contact handling
- Merge cautiously: add group membership and fill empty fields, but never overwrite existing data (name, phone, notes, etc.)
- Match on any email address on a contact card to prevent duplicates (not just primary email)

### Group handling
- Contact groups (Imbox, Feed, Paper Trail, Jail) must pre-exist in Fastmail — fail loudly if missing (config error)
- Verify all configured groups resolve to CardDAV URIs at startup — fast feedback on typos or missing groups
- One group per contact — no multi-group membership
- Re-triage in v1: if a sender is already in a group and gets triaged to a different destination, skip processing, apply @MailroomError label, keep triage label on the email for context

### @MailroomError label
- @MailroomError is a Fastmail label used as a user-visible error notification (the user is already looking at Fastmail, not at logs)
- Applied only for user-actionable errors (re-triage conflict, persistent failures), not transient issues
- Transient errors (network timeout, Fastmail temporarily down): retry silently for 3 poll cycles (~15 min), then escalate to @MailroomError
- @MailroomError must exist in Fastmail — verified at startup alongside other labels
- Error details go to structured logs; the label is the alert mechanism
- To retry: remove @MailroomError label from the email. The triage label is still on it, so the next poll picks it up

### Validation approach
- Human test script against live Fastmail — not automated integration tests
- Validation boundary: contact in correct group = Phase 2 success. Rules firing is outside app's control (manual Fastmail setup)
- Test script includes: (1) create contact with correct data, (2) verify contact in correct group, (3) verify existing contact not duplicated, (4) ETag conflict test with paused execution (edit contact in Fastmail, press Enter to continue — deterministic, not timing-dependent)
- Clear setup documentation for manual prerequisites (groups, rules, app password)

### Claude's Discretion
- ETag concurrency implementation details (retry strategy, backoff)
- vCard 3.0 field formatting specifics
- CardDAV REPORT query construction
- Loading/skeleton design for any CLI output
- Exact structured log format for CardDAV operations

</decisions>

<specifics>
## Specific Ideas

- @MailroomError label pattern: use Fastmail itself as the notification channel rather than relying on log monitoring. The user sees errors where they already look — their inbox.
- Human test script should have explicit pause points for manual verification steps (e.g., "Now edit this contact in Fastmail, then press Enter") rather than relying on timing.
- The merge-cautiously approach for existing contacts protects manually-curated contact data while still allowing Mailroom to fill in gaps.

</specifics>

<deferred>
## Deferred Ideas

- Programmatic Fastmail rule verification/creation via JMAP sieve extension — future version
- Display name accuracy for shared-sender addresses (e.g., noreply@dpd.com showing shipper name instead of carrier name) — low priority, routing works correctly regardless
- TRIAGE-11 (sender display name preservation) in REQUIREMENTS.md is related to the display name edge case

</deferred>

---

*Phase: 02-carddav-client-validation-gate*
*Context gathered: 2026-02-24*
