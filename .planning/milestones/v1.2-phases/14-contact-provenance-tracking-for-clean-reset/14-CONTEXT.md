# Phase 14: Contact Provenance Tracking for Clean Reset - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Track which contacts Mailroom created vs. merely annotated (adopted), enabling the reset command to delete created contacts entirely while only stripping notes and removing group memberships from pre-existing ones. Includes a config section rename, setup provisioning, and a triage pipeline fix for @MailroomWarning cleanup.

</domain>

<decisions>
## Implementation Decisions

### Tracking mechanism
- Dedicated CardDAV contact group for provenance tracking (not note-based heuristic)
- Group populated only when `create_contact()` fires (action: "created")
- Pre-existing contacts that get upserted are NEVER added to provenance group
- No retroactive migration — provenance tracking starts from this phase forward
- Provenance group membership is permanent across re-triage (creation origin doesn't change)
- Provenance group is invisible to triage pipeline: not in `resolved_categories`, not checked by `check_membership()`, not in sieve guidance

### Note format change
- Add a provenance line after the `— Mailroom —` header, before the triage history:
  - Created contacts: `Created by Mailroom`
  - Existing contacts (adopted): `Adopted by Mailroom`
- Rest of note format unchanged (triage history lines follow as before)
- Example (created):
  ```
  — Mailroom —
  Created by Mailroom
  Triaged to Feed on 2026-03-04
  ```
- Example (adopted/existing):
  ```
  — Mailroom —
  Adopted by Mailroom
  Triaged to Feed on 2026-03-04
  ```

### Config restructure
- Rename top-level `labels:` section to `mailroom:`
- Rename keys within:
  - `mailroom_error` → `label_error`
  - `mailroom_warning` → `label_warning`
  - `warnings_enabled` stays as-is
  - Add `provenance_group` key (configurable name, Claude picks default)
- No backward compatibility — app fails to start if config doesn't match expected schema
- Example:
  ```yaml
  mailroom:
    label_error: "@MailroomError"
    label_warning: "@MailroomWarning"
    warnings_enabled: true
    provenance_group: "Mailroom"
  ```

### Group design
- Single provenance group (no separate "adopted" group — note differentiates)
- Group name configurable via `mailroom.provenance_group` in config.yaml
- Validated at startup alongside category groups (fail fast if missing)
- Setup CLI creates it with `--apply`, reports in Mailroom section

### Reset behavior
- Contacts in provenance group + unmodified → DELETE from CardDAV
- Contacts in provenance group + user-modified → WARN:
  - Strip Mailroom note section
  - Remove from category groups
  - Remove from provenance group
  - Apply @MailroomWarning to all their emails (visual breadcrumb for user)
- Contacts NOT in provenance group + has Mailroom note → adopted contact:
  - Strip Mailroom note section
  - Remove from category groups
- "User-modified" detection: compare vCard fields against what Mailroom sets (FN, EMAIL, NOTE, UID, N, ORG). Extra fields (phone, address, etc.) = user-modified
- Reset operation order:
  1. Remove managed labels from emails (Feed, Imbox, etc.)
  2. Remove @MailroomWarning + @MailroomError from ALL emails (clean slate)
  3. Remove contacts from category groups
  4. For provenance + user-modified contacts: apply @MailroomWarning to their emails
  5. Remove warned contacts from provenance group
  6. Strip Mailroom notes from all annotated contacts
  7. Delete unmodified provenance contacts
- Second reset after warned contacts: contacts are no longer in provenance group, no Mailroom note, so they're invisible to reset. If Mailroom re-encounters them later, they're correctly treated as existing (adopted).

### Triage pipeline: @MailroomWarning cleanup
- On every successful triage, remove @MailroomWarning from ALL emails of that sender (not just triggering emails)
- If warning condition still exists after processing (e.g., name mismatch), reapply @MailroomWarning
- Idempotent: remove → process → conditionally reapply
- Fixes current behavior where @MailroomWarning accumulates forever
- @MailroomWarning does NOT block triage (only @MailroomError does) — this is intentional

### Setup & provisioning
- Setup CLI creates provenance group in Mailroom section (alongside @MailroomError, @MailroomWarning)
- Provenance group reported as `kind="mailroom"` in setup output
- Sieve guidance does NOT mention provenance group (no routing purpose)

### Claude's Discretion
- Default provenance group name (likely "Mailroom" for brevity)
- Exact "user-modified" detection logic (which vCard fields to compare)
- Implementation details for @MailroomWarning removal during triage (integrate into `_reconcile_email_labels` or separate step)
- Test structure and organization

</decisions>

<specifics>
## Specific Ideas

- "The group is more clear — one more group is not the end of the world"
- "If the user modifies a contact, it's almost like an existing contact now"
- "We apply @MailroomWarning so the user can look at the warning label, find the contact, and deal with it one by one"
- "If the user intentionally puts an action label, fair enough — they've taken an intentional action" (re: @MailroomWarning not blocking triage)
- "Remove the warning, process, and if there's still an issue, reapply — it's idempotent"
- Config rename: "labels" → "mailroom" because "these are all the mailroom things"
- Setup output should look exactly like the existing terraform-style layout with provenance group in the Mailroom section

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `create_contact()` (carddav.py:388): Returns contact dict — add provenance group membership here
- `upsert_contact()` (carddav.py:774): Returns `action: "created"` vs `action: "existing"` — decision point for provenance
- `add_to_group()` (carddav.py:463): Existing group membership method — reuse for provenance group
- `_strip_mailroom_note()` (resetter.py:52): Note stripping logic — already works, no changes needed
- `plan_reset()` / `apply_reset()` (resetter.py): Reset pipeline — needs provenance-aware logic
- `_reconcile_email_labels()` (screener.py:525): Touches all sender emails — candidate for @MailroomWarning removal
- `print_plan()` (reporting.py:71): Setup output — already has `kind="mailroom"` section

### Established Patterns
- ETag-based optimistic concurrency for CardDAV writes (GET → modify → PUT with If-Match → retry on 412)
- `validate_groups()` at startup — extend to include provenance group
- `MailroomSettings` pydantic model — rename `labels` → `mailroom` section
- Setup provisioner pattern: check existence → create if missing → report status

### Integration Points
- `upsert_contact()`: Add provenance group membership after `create_contact()` call
- `MailroomSettings.labels` → rename to `MailroomSettings.mailroom` (config model change)
- All references to `settings.labels.*` must update to `settings.mailroom.*`
- `validate_groups()`: Add provenance group to required groups list
- `plan_reset()` / `apply_reset()`: Add provenance-aware contact handling
- `_process_sender()`: Add @MailroomWarning removal before processing
- Setup provisioner: Add provenance group creation

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 14-contact-provenance-tracking-for-clean-reset*
*Context gathered: 2026-03-04*
