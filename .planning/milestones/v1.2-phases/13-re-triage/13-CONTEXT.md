# Phase 13: Re-triage - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Applying a triage label to an already-grouped sender moves them to the new contact group with full email label reconciliation and auditable triage history in contact notes. This replaces the current already-grouped error behavior. Initial triage for new senders is unchanged.

</domain>

<decisions>
## Implementation Decisions

### Re-filing scope (label reconciliation)
- Fetch ALL emails from the sender (any mailbox, not just old destination)
- Remove ALL managed destination labels (every `destination_mailbox` from config: Feed, Paper Trail, Imbox, Billboard, Truck, Person, Jail, etc.)
- Also remove Screener label (self-healing: if a triaged sender somehow has emails in Screener, clean them up)
- Apply the NEW additive labels (child + parent chain destinations for the new category)
- Non-managed labels are NEVER touched (e.g., user-created labels like "Project ABC")
- Idempotent: even if emails lost labels manually, the correct new labels get applied
- This is a full reconciliation, not a move — strip all managed labels, apply correct ones

### Inbox handling on re-triage
- Inbox is never removed during re-triage
- Inbox is added ONLY to emails that are currently in Screener AND the new category has `add_to_inbox=true`
- This is location-based (same rule as initial triage): Screener presence triggers `add_to_inbox`, not the operation type
- In practice, triaged senders should have no Screener emails — but if they do (broken state), this self-heals

### Contact group reassignment
- Order: add-to-new FIRST, then remove-from-old (safe partial-failure — sender is in both groups briefly, never zero)
- Remove sender from old child group + old ancestor groups that are NOT in the new chain
- Add sender to new child group + new ancestor groups
- Groups shared between old and new chains are left untouched (no remove+re-add churn)

### Same-group re-triage
- Treat identically to cross-group re-triage: run full label reconciliation
- Self-heals any label drift (emails that lost their destination label)
- Logged as `group_reassigned` with `same_group: true` flag (same event type, one code path)

### Structured logging
- Re-triage logged as `group_reassigned` event with `old_group`, `new_group`, `same_group` fields
- Same-group: `same_group: true`, `old_group == new_group`
- Cross-group: `same_group: false`

### Contact note format (triage history)
- Header line: `— Mailroom —`
- Initial triage: `Triaged to [group] on [date]`
- Re-triage (any): `Re-triaged to [new_group] on [date]`
- Same format for same-group and cross-group — the "from" group is implicit from the line above
- Notes are appended chronologically, building a triage history log
- Replaces current "Added by Mailroom" and "Updated by Mailroom" note patterns
- Example:
  ```
  — Mailroom —
  Triaged to Feed on 2026-03-03
  Re-triaged to Imbox on 2026-03-04
  Re-triaged to Imbox on 2026-03-05
  ```

### Already-grouped check replacement
- `_check_already_grouped()` and `_apply_error_label()` for already-grouped senders are replaced by re-triage logic
- `_detect_conflicts()` (different labels on same sender) is UNCHANGED — that's a different concern
- `@MailroomError` is no longer applied for already-grouped senders

### Human test strategy
- test_9_already_grouped.py: add early exit at top redirecting to test_17 ("This test validates an outdated requirement. Run test_17_retriage.py instead.")
- test_17_retriage.py: new test validating re-triage workflow end-to-end (RTRI-05)
- Test scenarios: Claude's discretion (cross-group move is the core path; same-group re-triage is a secondary scenario)

### Claude's Discretion
- `remove_from_group()` CardDAV implementation details (ETag conflict retry pattern, mirroring `add_to_group()`)
- How to identify "managed labels" for the reconciliation strip (derive from config at runtime)
- JMAP query strategy for fetching all emails from a sender across all mailboxes
- Test structure and organization for unit tests
- Exact test scenarios for test_17 (which groups, how many emails, verification checks)

</decisions>

<specifics>
## Specific Ideas

- "Mailboxes are labels in Fastmail — re-triage is about applying and removing labels, not moving emails"
- "Non-managed labels should be untouched — if I have a label called Project ABC, it's not part of the config"
- "If Screener emails exist for a triaged sender, that's a half-broken state — re-triage should self-heal by removing Screener and applying correct labels"
- "For add_to_inbox on Screener emails during re-triage: makes sure I actually review them — they pop in my inbox"
- Contact note: "— Mailroom —" header signifies the start of the Mailroom section, helps with programmatic parsing
- test_9: "for historical consistency, have something at the very beginning that exits early and says this test is testing an outdated requirement"

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_check_already_grouped()` (screener.py:460): finds sender's current group — logic reusable for detecting re-triage vs initial triage
- `_get_destination_mailbox_ids()` (screener.py:439): already walks parent chain for additive labels — reusable for new destination labels
- `get_parent_chain()` (config.py): walks parent chain for a category — reusable for both old and new chain computation
- `add_to_group()` (carddav.py:459): adds contact to group with ETag retry — pattern to mirror for `remove_from_group()`
- `check_membership()` (carddav.py:533): finds which group a contact is in — useful for detecting re-triage
- `upsert_contact()` (carddav.py:577): handles NOTE field — needs modification for triage history format
- `batch_move_emails()` (jmap.py): batch applies mailbox label changes — reusable for reconciliation
- `resolved_categories` (config.py): lists all categories — source for "managed labels" set
- `test_9_already_grouped.py`: existing human test structure to reference for test_17

### Established Patterns
- ETag-based optimistic concurrency for CardDAV writes (GET → modify → PUT with If-Match → retry on 412)
- Retry safety: triage label removed LAST, so failures auto-retry next poll
- `_process_sender()` step-by-step flow: extract → check → upsert → sweep → remove label
- Structured logging with `structlog.bind()` for per-sender context

### Integration Points
- `_process_sender()` (screener.py:359): main method to modify — replace already-grouped error path with re-triage path
- `_check_already_grouped()` → becomes re-triage detection (returns old group info instead of triggering error)
- `CardDAVClient`: needs new `remove_from_group()` method
- `upsert_contact()`: NOTE handling needs update for triage history format
- `_get_destination_mailbox_ids()`: may need variant that takes a category name instead of label_name
- `JMAPClient`: needs method to query all emails from a sender (no mailbox filter) for reconciliation

</code_context>

<deferred>
## Deferred Ideas

- Sweep workflow: re-label archived emails by contact group membership — far-future idea (#5), different from re-triage
- Update the out-of-scope entry "Sweep ALL historical sender emails on re-triage" — re-triage now intentionally fetches all emails for reconciliation

</deferred>

---

*Phase: 13-re-triage*
*Context gathered: 2026-03-03*
