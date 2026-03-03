# Phase 13: Re-triage - Research

**Researched:** 2026-03-03
**Domain:** Screener workflow re-triage (JMAP label reconciliation + CardDAV group reassignment)
**Confidence:** HIGH

## Summary

Phase 13 replaces the current already-grouped error behavior with a re-triage flow that moves senders between contact groups and reconciles all their email labels. The implementation is well-bounded: it modifies `_process_sender()` in `screener.py`, adds `remove_from_group()` to `carddav.py`, needs a new JMAP method to query all emails from a sender across all mailboxes (current `query_emails` requires `mailbox_id`), and updates the contact note format from "Added/Updated by Mailroom" to a chronological triage history log.

The codebase is in good shape for this work: all 330 tests pass, the architecture is clean (workflow orchestration in screener.py, protocol details in clients), and every pattern needed for re-triage (ETag retry, parent chain walking, batch email operations, structured logging) already exists and just needs to be composed differently. The main complexity is the label reconciliation logic -- stripping ALL managed labels and applying the correct new ones -- which must be correct and idempotent.

**Primary recommendation:** Implement as 2-3 waves: (1) CardDAV additions (remove_from_group, triage history notes) + JMAP query-all-emails method, (2) screener.py re-triage logic replacing already-grouped error path, (3) human test_17 + test_9 early exit.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Re-filing scope: fetch ALL emails from sender (any mailbox), remove ALL managed destination labels, also remove Screener label (self-healing), apply NEW additive labels. Non-managed labels NEVER touched. Full reconciliation, not a move.
- Inbox handling: Inbox never removed during re-triage. Inbox added ONLY to emails currently in Screener AND new category has add_to_inbox=true. Location-based (same rule as initial triage).
- Contact group reassignment order: add-to-new FIRST, then remove-from-old. Remove from old child + old ancestor groups NOT in new chain. Groups shared between old and new chains left untouched.
- Same-group re-triage: treated identically to cross-group -- full label reconciliation. Logged as group_reassigned with same_group: true flag.
- Structured logging: group_reassigned event with old_group, new_group, same_group fields.
- Contact note format: "-- Mailroom --" header, "Triaged to [group] on [date]" for initial, "Re-triaged to [new_group] on [date]" for subsequent. Chronological append. Replaces current "Added/Updated by Mailroom" patterns.
- Already-grouped check replacement: _check_already_grouped() and _apply_error_label() for already-grouped senders replaced by re-triage. _detect_conflicts() unchanged. @MailroomError no longer applied for already-grouped.
- Human test strategy: test_9 gets early exit redirecting to test_17. test_17_retriage.py validates end-to-end.

### Claude's Discretion
- remove_from_group() CardDAV implementation details (ETag conflict retry pattern, mirroring add_to_group())
- How to identify "managed labels" for the reconciliation strip (derive from config at runtime)
- JMAP query strategy for fetching all emails from a sender across all mailboxes
- Test structure and organization for unit tests
- Exact test scenarios for test_17

### Deferred Ideas (OUT OF SCOPE)
- Sweep workflow: re-label archived emails by contact group membership -- far-future idea, different from re-triage
- Update out-of-scope entry about sweeping historical emails
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RTRI-01 | Applying a triage label to an already-grouped sender moves them to the new contact group | Modify `_process_sender()` to detect existing group and branch to re-triage flow instead of error path. Use `_check_already_grouped()` return value as old_group. CardDAV `remove_from_group()` new method needed. |
| RTRI-02 | Re-triaged sender's emails re-filed by fetching ALL emails from contact and applying new additive labels | New JMAP method `query_emails_by_sender()` (no mailbox filter). New `batch_reconcile_emails()` method or reuse existing `batch_move_emails` with different signature. Managed labels derived from `resolved_categories`. |
| RTRI-03 | Re-triage logged as group_reassigned structured event with old and new group names | Structured logging already established -- add new event type with old_group, new_group, same_group fields via `structlog.bind()`. |
| RTRI-04 | Contact note captures triage history | Modify `upsert_contact()` and `create_contact()` NOTE handling to use new format: "-- Mailroom --" header + chronological entries. |
| RTRI-05 | Human integration test validates re-triage workflow end-to-end | New `test_17_retriage.py` following existing human test patterns. test_9 gets early-exit redirect. |
| RTRI-06 | add_to_inbox only adds Inbox to emails from Screener at triage time -- re-triage does NOT re-add Inbox | Reconciliation must check each email's current mailboxIds for Screener presence before deciding on Inbox. Or simpler: reconciliation NEVER adds Inbox (only initial triage from Screener does). |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| structlog | (existing) | Structured event logging | Already used for all workflow events |
| vobject | (existing) | vCard parsing/serialization | Already used for CardDAV contact ops |
| httpx | (existing) | HTTP client for JMAP/CardDAV | Already used in both clients |
| pytest | (existing) | Unit test framework | 330 existing tests |
| pytest-httpx | (existing) | HTTP mocking for CardDAV tests | Already used in test_carddav_client.py |

### Supporting
No new libraries needed. All implementation uses existing dependencies.

## Architecture Patterns

### Current _process_sender Flow (to be modified)
```
_process_sender(sender, emails, sender_names)
  1. Extract label_name, email_ids, category, group_name
  2. _check_already_grouped(sender, group_name) -> existing_group
     - If existing_group: apply @MailroomError and RETURN  <-- REPLACE THIS
  3. upsert_contact(sender, display_name, group_name)
  4. Add to ancestor groups (parent chain)
  5. Sweep Screener emails -> batch_move_emails
  6. Remove triage label (LAST step)
```

### New _process_sender Flow
```
_process_sender(sender, emails, sender_names)
  1. Extract label_name, email_ids, category, group_name
  2. Detect re-triage: search_by_email -> check_membership (ALL groups, not excluding target)
     - If no existing contact: is_retriage=False, old_group=None
     - If contact exists but not in any group: is_retriage=False
     - If contact in target group: is_retriage=True, old_group=target_group (same-group)
     - If contact in different group: is_retriage=True, old_group=other_group
  3. Upsert contact with triage history note
  4. Contact group management:
     - If re-triage: add to new chain, remove from old-only groups
     - If initial triage: add to new chain (existing behavior)
  5. Email label reconciliation:
     - If re-triage: fetch ALL emails from sender, strip managed labels, apply new additive labels
     - If initial triage: sweep Screener only (existing behavior)
  6. Remove triage label (LAST step)
```

### Pattern 1: CardDAV remove_from_group (mirrors add_to_group)
**What:** Remove a contact UID from a group's X-ADDRESSBOOKSERVER-MEMBER list
**When to use:** Re-triage contact group reassignment -- removing from old groups
**Example:**
```python
# Source: carddav.py add_to_group() pattern (lines 459-531)
def remove_from_group(
    self,
    group_name: str,
    contact_uid: str,
    max_retries: int = 3,
) -> str:
    """Remove a contact from a group with ETag-based optimistic concurrency."""
    self._require_connection()
    group_info = self._groups[group_name]
    href = group_info["href"]
    group_url = f"https://{self._hostname}{href}"
    member_urn = f"urn:uuid:{contact_uid}"

    for attempt in range(max_retries):
        resp = self._http.get(group_url)
        resp.raise_for_status()
        current_etag = resp.headers.get("etag", "")
        card = vobject.readOne(resp.text)

        existing_members = card.contents.get("x-addressbookserver-member", [])
        existing_urns = [m.value for m in existing_members]
        if member_urn not in existing_urns:
            return current_etag  # Already not a member -- idempotent

        # Remove the member entry
        card.contents["x-addressbookserver-member"] = [
            m for m in existing_members if m.value != member_urn
        ]

        put_resp = self._http.put(
            group_url,
            content=card.serialize().encode("utf-8"),
            headers={
                "Content-Type": "text/vcard; charset=utf-8",
                "If-Match": current_etag,
            },
        )
        if put_resp.status_code == 412:
            continue
        put_resp.raise_for_status()
        new_etag = put_resp.headers.get("etag", "")
        self._groups[group_name]["etag"] = new_etag
        return new_etag

    raise RuntimeError(
        f"Failed to remove member from group {group_name} "
        f"after {max_retries} retries (ETag conflict)"
    )
```

### Pattern 2: JMAP query all emails from sender (no mailbox filter)
**What:** Query Email/query with only a "from" filter, no "inMailbox" constraint
**When to use:** Re-triage email reconciliation -- need ALL emails from sender
**Example:**
```python
# Source: jmap.py query_emails() pattern (lines 191-240), modified
def query_emails_by_sender(self, sender: str, limit: int = 100) -> list[str]:
    """Query all email IDs from a sender across all mailboxes."""
    email_filter: dict = {"from": sender}
    all_ids: list[str] = []
    position = 0

    while True:
        responses = self.call([
            ["Email/query", {
                "accountId": self.account_id,
                "filter": email_filter,
                "limit": limit,
                "position": position,
            }, "q0"]
        ])
        data = responses[0][1]
        ids = data["ids"]
        total = data["total"]
        all_ids.extend(ids)
        if len(all_ids) >= total:
            break
        position = len(all_ids)
    return all_ids
```

### Pattern 3: Label Reconciliation (new batch operation)
**What:** Strip all managed labels from emails and apply new additive labels
**When to use:** Re-triage email re-filing
**Key insight:** Use JMAP patch syntax to remove multiple labels and add multiple labels in a single Email/set per email.
```python
# Build JMAP patch for each email:
patch = {}
# Remove all managed destination labels
for managed_id in managed_mailbox_ids:
    patch[f"mailboxIds/{managed_id}"] = None
# Remove Screener label (self-healing)
patch[f"mailboxIds/{screener_id}"] = None
# Add new additive labels
for new_id in new_destination_ids:
    patch[f"mailboxIds/{new_id}"] = True
# Inbox handling: only add if email is currently in Screener AND add_to_inbox
```

### Pattern 4: Managed Labels Set (derived from config at runtime)
**What:** Set of all mailbox IDs that Mailroom manages (destination mailboxes for all categories)
**When to use:** Determining which labels to strip during reconciliation
```python
# Source: config.py resolved_categories (line 412)
managed_mailboxes = {c.destination_mailbox for c in self._settings.resolved_categories}
# Convert to IDs using self._mailbox_ids
managed_mailbox_ids = {self._mailbox_ids[name] for name in managed_mailboxes}
```

### Pattern 5: Contact Note Triage History
**What:** New NOTE format with header and chronological entries
**When to use:** Both create_contact and upsert_contact NOTE handling
```python
# New contact:
note = f"-- Mailroom --\nTriaged to {group_name} on {date.today().isoformat()}"

# Existing contact with old-format note:
# If note doesn't start with "-- Mailroom --", preserve it and add section
note = f"{existing_note}\n\n-- Mailroom --\nRe-triaged to {group_name} on {date.today().isoformat()}"

# Existing contact with new-format note (already has Mailroom section):
# Append new entry
note = f"{existing_note}\nRe-triaged to {group_name} on {date.today().isoformat()}"
```

### Pattern 6: Smart Group Reassignment (shared chain optimization)
**What:** Only remove from groups unique to old chain, skip shared groups
**When to use:** Cross-group re-triage where old and new parent chains overlap
```python
old_chain_groups = {c.contact_group for c in get_parent_chain(old_category, resolved_map)}
new_chain_groups = {c.contact_group for c in get_parent_chain(new_category, resolved_map)}

# Groups to remove: in old chain but NOT in new chain
remove_groups = old_chain_groups - new_chain_groups
# Groups to add: in new chain but NOT in old chain
add_groups = new_chain_groups - old_chain_groups
# Groups in both: leave untouched (no churn)
```

### Anti-Patterns to Avoid
- **Remove-then-add for groups:** NEVER remove from all old groups first then add to new groups. Always add-to-new FIRST, then remove-from-old. This ensures the sender is never in zero groups during a partial failure.
- **Moving emails instead of reconciling labels:** Fastmail mailboxes are labels. Don't think of "moving" emails. Think of adjusting which labels (mailboxIds) are set on each email.
- **Checking add_to_inbox on re-triage:** Re-triage NEVER adds Inbox to emails. The only exception: emails that happen to be in Screener (broken state self-healing) AND the new category has add_to_inbox=true. This is location-based, not operation-based.
- **Removing Inbox during reconciliation:** Inbox is NEVER removed during re-triage. Only managed destination labels + Screener are stripped.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ETag retry for group writes | Custom retry loop | Mirror `add_to_group()` exactly | Pattern proven in production, handles 412 correctly |
| Parent chain walking | Custom tree traversal | `get_parent_chain()` from config.py | Already handles all chain shapes, tested |
| Batch email label updates | One-by-one Email/set | `batch_move_emails` pattern with BATCH_SIZE chunks | Respects Fastmail's maxObjectsInSet limit |
| Managed label set | Hardcoded label list | `resolved_categories` from config | Automatically adapts to config changes |

## Common Pitfalls

### Pitfall 1: Inbox removal during reconciliation
**What goes wrong:** Reconciliation strips "all managed labels" and accidentally includes Inbox
**Why it happens:** Inbox appears in `_get_destination_mailbox_ids` for categories with add_to_inbox
**How to avoid:** The "managed labels" set is ONLY destination_mailbox values from resolved_categories. Inbox is NOT a destination mailbox (CFG-02 bans it). The managed set will never include Inbox. Screener is added separately for self-healing.
**Warning signs:** Emails disappearing from Inbox after re-triage

### Pitfall 2: check_membership behavior change
**What goes wrong:** Current `_check_already_grouped()` calls `check_membership(uid, exclude_group=target_group)` which skips the target group. For re-triage detection, we need to find which group the contact IS in, including the target group (for same-group detection).
**Why it happens:** The current check_membership API was designed for "is this contact in a DIFFERENT group" detection.
**How to avoid:** For re-triage detection, call `check_membership(uid)` without exclude_group, or iterate `_groups` to find ALL memberships. Alternatively, repurpose `_check_already_grouped` to return old_group (any group, including same).
**Warning signs:** Same-group re-triage not being detected

### Pitfall 3: Partial failure during group reassignment leaves contact in extra groups
**What goes wrong:** Add-to-new succeeds but remove-from-old fails, leaving contact in both old and new groups
**Why it happens:** Network errors, ETag conflicts exhausting retries
**How to avoid:** This is the SAFE direction per the locked decision. Contact in extra groups means sieve rules file to both destinations -- suboptimal but not data-losing. The next re-triage attempt will clean up. Log the partial failure clearly.
**Warning signs:** Contact appearing in multiple unexpected group mailboxes

### Pitfall 4: Screener label on already-triaged emails
**What goes wrong:** Reconciliation doesn't remove Screener label from emails that somehow got it
**Why it happens:** Bug in sieve rules, manual user action, or email client behavior
**How to avoid:** The locked decision explicitly includes Screener removal as self-healing. Add Screener mailbox ID to the "labels to remove" set alongside managed destination labels.
**Warning signs:** Emails appearing in both Screener and a destination mailbox

### Pitfall 5: JMAP "from" filter semantics
**What goes wrong:** JMAP "from" filter matches substring or display name, not exact email address
**Why it happens:** JMAP RFC 8621 specifies that "from" is a text filter matching "From" header content
**How to avoid:** The existing `query_emails()` already uses `"from": sender` and this works correctly with Fastmail in production (confirmed by existing human tests). The same filter without `inMailbox` should work identically.
**Warning signs:** Re-triage reconciliation affecting emails from different senders with similar addresses

### Pitfall 6: vobject X-ADDRESSBOOKSERVER-MEMBER removal edge case
**What goes wrong:** Removing the last member from a group vCard causes serialization issues
**Why it happens:** vobject may handle empty content lists differently
**How to avoid:** After filtering, if the member list is empty, either set `card.contents["x-addressbookserver-member"] = []` or delete the key entirely. Test this edge case explicitly.
**Warning signs:** 400/500 errors when PUTting group vCard with no members

### Pitfall 7: Note format migration for existing contacts
**What goes wrong:** Existing contacts have "Added by Mailroom on..." notes. Re-triage appends new format without "-- Mailroom --" header.
**Why it happens:** create_contact() was not updated to use new format, or migration logic not considered
**How to avoid:** When re-triaging an existing contact whose note uses the OLD format, prepend the "-- Mailroom --" header and convert the existing "Added by Mailroom on DATE" to "Triaged to [old_group] on DATE" before appending the re-triage line. OR simpler: just add the Mailroom header + re-triage entry, treating the old note as non-Mailroom content.
**Warning signs:** Contact notes with mixed old/new formats

## Code Examples

### Re-triage Detection (replacing _check_already_grouped)
```python
# Source: screener.py _check_already_grouped() pattern (lines 460-486)
# Modified: returns (contact_uid, old_group) or (None, None)
def _detect_retriage(self, sender: str) -> tuple[str | None, str | None]:
    """Detect if sender is already in a contact group.

    Returns:
        (contact_uid, group_name) if sender is in a group.
        (None, None) if sender has no contact or is not in any group.
    """
    results = self._carddav.search_by_email(sender)
    if not results:
        return None, None

    card = vobject.readOne(results[0]["vcard_data"])
    contact_uid = card.uid.value

    # Check ALL groups (no exclude_group)
    group = self._carddav.check_membership(contact_uid)
    return contact_uid, group
```

### Label Reconciliation Logic
```python
# Build the set of managed mailbox IDs to strip
managed_names = {c.destination_mailbox for c in self._settings.resolved_categories}
managed_ids = {self._mailbox_ids[name] for name in managed_names}
screener_id = self._mailbox_ids[self._settings.triage.screener_mailbox]

# Fetch current mailboxIds for each email to check Screener presence
# (needed for add_to_inbox location-based check)
email_data = self._jmap.get_email_mailboxes(email_ids)  # new method or use Email/get

# Build per-email patch
for email_id in all_sender_emails:
    patch = {}
    # Strip all managed labels
    for mid in managed_ids:
        patch[f"mailboxIds/{mid}"] = None
    # Strip Screener (self-healing)
    patch[f"mailboxIds/{screener_id}"] = None
    # Apply new additive labels
    for new_id in new_destination_ids:
        patch[f"mailboxIds/{new_id}"] = True
    # Inbox: only if email is currently in Screener AND add_to_inbox
    if category.add_to_inbox and screener_id in email_data[email_id]:
        inbox_id = self._mailbox_ids["Inbox"]
        patch[f"mailboxIds/{inbox_id}"] = True
```

### Structured Logging for Re-triage
```python
# Source: screener.py structlog patterns
log.info(
    "group_reassigned",
    sender=sender,
    old_group=old_group,
    new_group=group_name,
    same_group=(old_group == group_name),
    emails_reconciled=len(all_sender_emails),
)
```

### Group Chain Diff
```python
resolved_map = {c.name: c for c in self._settings.resolved_categories}

# Find the old category from old_group name
old_category = next(
    (c for c in self._settings.resolved_categories if c.contact_group == old_group),
    None,
)

new_chain = get_parent_chain(category.name, resolved_map)
old_chain = get_parent_chain(old_category.name, resolved_map) if old_category else []

new_groups = {c.contact_group for c in new_chain}
old_groups = {c.contact_group for c in old_chain}

# Add to new-only groups
for c in new_chain:
    if c.contact_group not in old_groups:
        self._carddav.add_to_group(c.contact_group, contact_uid)

# Remove from old-only groups
for c in old_chain:
    if c.contact_group not in new_groups:
        self._carddav.remove_from_group(c.contact_group, contact_uid)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Already-grouped -> @MailroomError | Already-grouped -> re-triage | Phase 13 (this) | Sender can be moved between categories without manual cleanup |
| "Added by Mailroom on DATE" notes | "-- Mailroom --" header + history log | Phase 13 (this) | Auditable triage history with chronological entries |
| Sweep from Screener only | Full label reconciliation (all mailboxes) | Phase 13 (this) | Re-triage correctly updates all emails, not just unsorted ones |

**Deprecated/outdated:**
- `_check_already_grouped()` returning different-group as error -> replaced by re-triage detection
- `_apply_error_label()` for already-grouped -> no longer called for grouped senders
- "Added by Mailroom" / "Updated by Mailroom" note format -> replaced by triage history format

## Open Questions

1. **JMAP Email/get for mailboxIds of all sender emails -- batch size considerations**
   - What we know: Fastmail has a 500+ maxObjectsInSet limit, and current BATCH_SIZE is 100
   - What's unclear: For a sender with 1000+ emails, Email/get with properties=["mailboxIds"] may need pagination
   - Recommendation: Use same BATCH_SIZE chunking pattern as batch_move_emails. Alternatively, skip per-email Screener check since Screener emails for triaged senders are a broken-state edge case -- just apply reconciliation uniformly and only handle Inbox for the Screener case.

2. **Simplification opportunity: skip per-email Screener check**
   - What we know: The locked decision says Inbox is added only to emails in Screener. In practice, triaged senders should have NO Screener emails.
   - Recommendation: Implement the simpler path first: reconciliation NEVER adds Inbox. If an email is in Screener (broken state), it gets Screener removed and new labels applied but no Inbox. This matches "re-triage does NOT add Inbox to existing emails." The Screener-presence Inbox check only matters for initial triage. Planner should decide.

3. **Note format migration for contacts created before Phase 13**
   - What we know: Existing contacts have "Added by Mailroom on DATE" notes
   - What's unclear: Should we try to parse/convert old notes or just add the new section?
   - Recommendation: On re-triage of an old-format contact, just add the Mailroom section with re-triage entry. The old "Added by Mailroom" note becomes historical context. Don't try to parse/convert it.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, 330 tests passing) |
| Config file | `tests/conftest.py` (existing, with mock_settings and mock_mailbox_ids) |
| Quick run command | `python -m pytest tests/test_screener_workflow.py -x --tb=short -q` |
| Full suite command | `python -m pytest tests/ -x --tb=short -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RTRI-01 | Re-triage moves sender to new contact group | unit | `python -m pytest tests/test_screener_workflow.py -k "retriage" -x` | No -- Wave 0 |
| RTRI-01 | remove_from_group CardDAV operation | unit | `python -m pytest tests/test_carddav_client.py -k "remove_from_group" -x` | No -- Wave 0 |
| RTRI-02 | Email re-filing with label reconciliation | unit | `python -m pytest tests/test_screener_workflow.py -k "reconcil" -x` | No -- Wave 0 |
| RTRI-02 | query_emails_by_sender JMAP operation | unit | `python -m pytest tests/test_jmap_client.py -k "query_emails_by_sender" -x` | No -- Wave 0 |
| RTRI-03 | group_reassigned structured logging | unit | `python -m pytest tests/test_screener_workflow.py -k "group_reassigned" -x` | No -- Wave 0 |
| RTRI-04 | Triage history in contact notes | unit | `python -m pytest tests/test_carddav_client.py -k "triage_history" -x` | No -- Wave 0 |
| RTRI-05 | End-to-end re-triage human test | manual-only | `python human-tests/test_17_retriage.py` | No -- Wave 0 |
| RTRI-06 | add_to_inbox Screener-only behavior | unit | `python -m pytest tests/test_screener_workflow.py -k "inbox_retriage" -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x --tb=short -q` (full suite, ~1s)
- **Per wave merge:** `python -m pytest tests/ -x --tb=short -q` (same -- fast enough)
- **Phase gate:** Full suite green + human test_17 passes

### Wave 0 Gaps
- [ ] New tests in `tests/test_screener_workflow.py` for re-triage scenarios (replacing TestAlreadyGroupedDifferentGroup behavior)
- [ ] New tests in `tests/test_carddav_client.py` for `remove_from_group()`
- [ ] New tests in `tests/test_jmap_client.py` for `query_emails_by_sender()`
- [ ] New tests in `tests/test_carddav_client.py` for triage history note format
- [ ] `human-tests/test_17_retriage.py` -- new human integration test
- [ ] `human-tests/test_9_already_grouped.py` -- early exit redirect

### Existing Tests That Will Need Updates
- `TestAlreadyGroupedDifferentGroup` (test_screener_workflow.py:761) -- currently asserts error label applied; must change to assert re-triage behavior
- `TestAlreadyGroupedSameGroup` (test_screener_workflow.py:823) -- currently asserts normal processing; must change to assert same-group re-triage with reconciliation
- `TestProcessSenderStepOrder` (test_screener_workflow.py:691) -- step order will change for re-triage path
- `upsert_contact` tests in test_carddav_client.py -- NOTE format changes

## Sources

### Primary (HIGH confidence)
- `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/workflows/screener.py` -- current _process_sender, _check_already_grouped, _get_destination_mailbox_ids
- `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/clients/carddav.py` -- add_to_group (pattern for remove_from_group), upsert_contact, check_membership, create_contact
- `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/clients/jmap.py` -- query_emails, batch_move_emails, remove_label
- `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/core/config.py` -- get_parent_chain, resolved_categories, ResolvedCategory
- `/Users/flo/Work/Private/Dev/Services/mailroom/tests/test_screener_workflow.py` -- existing test patterns, mock fixtures
- `/Users/flo/Work/Private/Dev/Services/mailroom/tests/conftest.py` -- mock_settings, mock_mailbox_ids fixtures
- `/Users/flo/Work/Private/Dev/Services/mailroom/docs/WIP.md` -- re-triage sweep logic documentation
- `/Users/flo/Work/Private/Dev/Services/mailroom/.planning/phases/13-re-triage/13-CONTEXT.md` -- locked decisions

### Secondary (MEDIUM confidence)
- JMAP RFC 8621 Email/query filter semantics -- "from" filter works without "inMailbox" (confirmed by existing production usage of "from" filter in query_emails)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all patterns exist in codebase
- Architecture: HIGH -- clear modification points identified, existing patterns to mirror
- Pitfalls: HIGH -- derived from direct code reading and understanding of JMAP/CardDAV semantics
- Test strategy: HIGH -- existing test infrastructure is comprehensive, patterns clear

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable -- internal project, no external API changes expected)
