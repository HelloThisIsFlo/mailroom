# Feature Research: v1.2 Triage Pipeline v2

**Domain:** Email triage automation — inbox flag separation, additive parent labels, label-based scanning, re-triage
**Researched:** 2026-03-02
**Confidence:** HIGH — all features derived from codebase analysis, confirmed todos, and explicit milestone spec. No external API unknowns: JMAP multi-mailbox queries are already proven patterns in this codebase.

---

## Context

v1.1 is shipped. This research covers ONLY the new features for v1.2. The existing pipeline (poll, triage, contact upsert, sweep, EventSource push, config.yaml, Helm) is already built and tested.

The four new features address separate pain points:

1. **Inbox flag separation** — decouple "show in Inbox" from "where to file"
2. **Additive parent labels** — children become independent categories that also propagate parent labels upward
3. **Label-based scanning** — query triage label mailboxes directly instead of filtering Screener
4. **Re-triage** — move sender between contact groups, re-file their emails

Plus a fifth enabling item:

5. **Tech debt cleanup** — 4 carry-forward items from v1.1 audit, must clear before new features

---

## Feature Landscape

### Table Stakes (Must Ship for v1.2 to Deliver)

These features are what the milestone promises. Missing any = milestone incomplete.

---

#### Feature 1: Separate `add_to_inbox` Flag from `destination_mailbox`

| Aspect | Detail |
|--------|--------|
| **Why expected** | Current `Imbox` category uses `destination_mailbox: Inbox` to appear in Inbox. This conflates filing destination with inbox visibility. It blocks valid configs like "file to Feed mailbox AND show in Inbox" — currently impossible without making Feed's destination Inbox itself. |
| **Complexity** | LOW-MEDIUM — config model change (new field), resolution logic update, screener pipeline update, validation tightening |
| **Dependencies** | Existing `TriageCategory` / `ResolvedCategory` / `resolve_categories()` in `config.py`. Existing `_get_destination_mailbox_ids()` in `screener.py`. |

**Expected behavior:**
- `add_to_inbox: true` → email is added to Inbox label *in addition to* its destination mailbox
- `destination_mailbox` is never `"Inbox"` — validation rejects this explicitly with a clear error pointing to `add_to_inbox`
- `destination_mailbox` may be null/empty (for inbox-only categories, no separate mailbox)
- `add_to_inbox` participates in parent inheritance (open question: should it inherit? Likely yes — Person as child of Imbox should also show in Inbox)
- Default: `add_to_inbox: false` (existing behavior for Feed, Paper Trail, Jail)
- Default Imbox category changes from `destination_mailbox: Inbox` → `add_to_inbox: true`

**Edge cases:**
- `add_to_inbox: true` + `destination_mailbox: null` → inbox-only (no sweep to named mailbox)
- `add_to_inbox: true` + `destination_mailbox: Feed` → email appears in both Feed and Inbox
- `destination_mailbox: Inbox` in config.yaml → startup validation error with migration hint
- `required_mailboxes` property: Inbox is always required; skip empty `destination_mailbox`

**Changes to existing code:**
- `TriageCategory`: add `add_to_inbox: bool = False`
- `ResolvedCategory`: add `add_to_inbox: bool`
- `resolve_categories()`: propagate `add_to_inbox` through parent inheritance chain
- `_validate_categories()`: reject `destination_mailbox: "Inbox"` explicitly
- `screener.py._get_destination_mailbox_ids()`: include Inbox ID in result when `add_to_inbox` is true
- `MailroomSettings.required_mailboxes`: skip null `destination_mailbox`; Inbox always included
- `_default_categories()`: Imbox → `add_to_inbox=True`, remove `destination_mailbox="Inbox"`
- `config.yaml`: update Imbox category

---

#### Feature 2: Additive Parent Label Propagation

| Aspect | Detail |
|--------|--------|
| **Why expected** | Current `parent` field means "inherit parent's contact_group and destination_mailbox." In practice this makes children share the parent's group/mailbox rather than having their own identity. The intended use case (Person as a distinct category that also shows in Imbox view) requires child categories to be fully independent with parent labels additive, not overriding. |
| **Complexity** | MEDIUM — config model change (new `parent_labels` computed field), resolution logic simplification, screener pipeline adds a label-apply step, setup provisioner/sieve_guidance updates |
| **Dependencies** | Feature 1 (the two config changes are best shipped together — both touch `resolve_categories()`, `ResolvedCategory`, validation). Feature 3 (label-based scanning must handle the case where an email has *both* child and parent labels). |

**New semantics:**
- A child category is a **fully independent category**: own `@ToX` triage label, own contact group, own destination mailbox — all derived from its name as normal
- The only thing `parent` adds: when triaging, *also apply* all ancestor labels to the email
- `Billboard` (child of Paper Trail): email filed to Billboard mailbox, gets `@ToBillboard` label AND `@ToPaperTrail` label → email appears in both Billboard and Paper Trail views
- `Person` (child of Imbox): own Person contact group, Person mailbox, gets `@ToPerson` AND `@ToImbox` labels

**Parent chain resolution:**
- `ResolvedCategory` gains `parent_labels: list[str]` — computed field, ordered from immediate parent to root
- `resolve_categories()` builds this by walking the ancestor chain for each category
- Circular reference detection already exists; remains unchanged
- Shared-contact-group validation from `_validate_categories()` is removed or relaxed (children no longer share parent's group)

**What is removed from current code:**
- `contact_group` inheritance from parent (lines 235-241 in `config.py`)
- `destination_mailbox` inheritance from parent (lines 243-244 in `config.py`)
- Second-pass resolution simplifies: no longer merges parent fields, only builds `parent_labels`

**Screener pipeline change:**
- After filing to destination, call `apply_parent_labels(email_id, category.parent_labels)` for each triaged email
- This is a new JMAP `Email/set` patch call: add each parent label's mailbox ID to the email's `mailboxIds`
- Placed before the final "remove triage label" step to maintain retry safety invariant

**Setup/sieve impact:**
- Provisioner now creates fully independent resources for each child (own mailbox, own contact group)
- Sieve guidance notes: child rule should also apply parent labels (multi-action sieve rule)
- Shared-group validation in `_validate_categories()` may need updating (children no longer legitimately share groups)

**Edge cases:**
- Category with no parent: `parent_labels = []`, no additional label application
- Deep nesting (A → B → C): C gets labels `[B's label, A's label]` — full chain
- Parent label mailbox missing: startup validation catches this since all categories' labels must exist
- Open question (decide during implementation): does `add_to_inbox` from Feature 1 inherit through the parent chain? Recommended: yes — if parent has `add_to_inbox: true`, child should too, since "Person is a subset of Imbox" implies inbox visibility

---

#### Feature 3: Label-Based Scanning (Not Screener-Scoped)

| Aspect | Detail |
|--------|--------|
| **Why expected** | Current `_collect_triaged()` calls `query_emails(screener_id, sender=sender)` for sweep — only sweeps emails in the Screener. Triage labels can appear on emails anywhere (re-labeled after archiving, re-triaged from another mailbox). Scanning by label mailbox ID is the correct JMAP pattern: query `inMailbox: <label_mailbox_id>` — this returns all emails with that label regardless of where they also live. |
| **Complexity** | LOW — the current code already queries by label mailbox ID in `_collect_triaged()` (lines 99-101 in `screener.py`). The change is in the sweep step (`_process_sender`), not collection. Collection already works correctly. |
| **Dependencies** | None — this is a targeted fix to `_process_sender`'s sweep query. Can be shipped independently. |

**Current behavior (what's wrong):**
- `_collect_triaged()`: queries `inMailbox: <label_id>` — already label-based, correct
- `_process_sender()` step 3: queries `inMailbox: <screener_id>, from: <sender>` — Screener-scoped sweep, WRONG
- Result: if a user applies `@ToFeed` to an email already in Feed (re-triage scenario), the sweep step finds no emails to move (they're not in Screener), processes contacts only, then removes the triage label — partial success

**New behavior:**
- Sweep step queries `inMailbox: <label_id>, from: <sender>` — finds all emails from this sender that have the triage label, regardless of which mailbox they're also in
- Then moves those emails to the destination (removing source label, adding destination)
- For re-triage: also removes the old category label if the sender was previously in a different group (handled by Feature 4)

**JMAP mechanics:**
- `Email/query` with `filter: { inMailbox: <label_id>, from: <sender> }` — proven pattern, already used in collection step
- Can batch all label queries per sender into a single JMAP request (one `methodCalls` array with multiple `Email/query` entries per label), but this optimization is likely a differentiator not a table stake

**Edge cases:**
- Same email has multiple triage labels (conflict case): already handled by `_detect_conflicts()` — those emails never reach the sweep step
- Email is in Screener AND has triage label: still works — sweep finds it via label query and moves it
- Label mailbox is empty: `query_emails()` returns `[]`, sweep skips, no error

---

#### Feature 4: Re-Triage (Contact Group Reassignment + Email Re-Filing)

| Aspect | Detail |
|--------|--------|
| **Why expected** | When a contact is already in Paper Trail and user applies `@ToJail`, current behavior is `@MailroomError` + stop. But this IS a valid user action: intentionally moving a sender between groups. The system should execute it and inform the user it happened via `@MailroomWarning`. |
| **Complexity** | MEDIUM — changes `_check_already_grouped()` handling in `_process_sender()`, adds CardDAV group membership removal, adds old-label sweep step |
| **Dependencies** | Feature 3 (label-based scanning makes re-filing work correctly when emails aren't in Screener). Should be shipped after or alongside Feature 3 since the re-file step relies on the corrected sweep logic. |

**New behavior:**
- `_check_already_grouped()` returns the sender's current group (unchanged)
- `_process_sender()`: when contact is in a *different* group, instead of erroring:
  1. Remove contact from old group (CardDAV)
  2. Add contact to new group (CardDAV) — via existing `upsert_contact()`
  3. Sweep: find all emails from this sender that have the OLD category label, move them to new destination
  4. Apply `@MailroomWarning` to triggering email(s) — informational, action taken
  5. Log `group_reassigned` event with `old_group`, `new_group`
  6. Remove triage label (last step, preserving retry safety)
- If sender is ALREADY in the target group: skip (idempotent, no warning)

**CardDAV mechanics:**
- Remove from old group: `CardDAVClient` needs a method to remove a contact UID from a group's `X-ADDRESSBOOKSERVER-MEMBER` list
- The existing `check_membership()` already identifies which group contains the contact — this provides the group name needed for removal
- Group membership is stored as vCard properties on the group object; removal requires a `PUT` with updated group vCard (ETag-safe)

**Old-label sweep:**
- Need to know the sender's old category label to sweep their emails
- Old group name → old category lookup via config (`contact_groups` → `ResolvedCategory` reverse map)
- If old category is not in config (user removed it): log warning, skip old-label sweep, still complete reassignment
- Old-label sweep: query `inMailbox: <old_label_id>, from: <sender>`, move to new destination

**Log event:**
```json
{"event": "group_reassigned", "sender": "foo@bar.com", "old_group": "Paper Trail", "new_group": "Jail", "emails_refiled": 3}
```

**Semantic fix:**
- Current code logs `already_grouped` as a `warning` but applies the error label — semantic mismatch noted in todo
- New: `already_grouped` with different group → reassignment → `@MailroomWarning`
- `already_grouped` with SAME group → no-op, no warning (was already handled as idempotent)

**Edge cases:**
- Sender has no emails with old label (already moved manually): old-label sweep finds nothing, reassignment still completes
- Old category not in current config: skip old-label sweep, log warning, still complete reassignment
- CardDAV failure during group removal: exception propagates to `_process_sender` try/except — triage label stays for retry
- Re-triage to same group (no-op): detected by `_check_already_grouped()` returning None (already handled correctly)
- Re-triage applies `@MailroomWarning` before removing triage label — existing warning label infrastructure used

---

#### Feature 5: Tech Debt Cleanup (Enabling Phase)

| Aspect | Detail |
|--------|--------|
| **Why expected** | 4 items from v1.1 audit (todo `2026-03-02-resolve-v1-1-tech-debt-carry-forward-in-v1-2.md`). Should be cleared before new features to avoid carrying forward stale artifacts into new work. |
| **Complexity** | LOW — all 4 items are small, targeted fixes with no design uncertainty |
| **Dependencies** | None — independent of the four main features |

**Items:**
1. Write `VERIFICATION.md` for Phase 09.1.1 (process gap only, no code change)
2. Fix `test_13_docker_polling.py` — pass poll interval via `config.yaml` mount instead of silently-ignored env var
3. Add `resolved_categories` public property on `MailroomSettings`, update `sieve_guidance.py` to use it
4. Remove 7 stale env var names from `conftest.py` cleanup list

**Note:** Item 3 (`resolved_categories` public property) is also directly useful for Feature 2 (additive labels) — the new `parent_labels` computation may need to walk resolved categories. Doing tech debt first unblocks the feature work cleanly.

---

### Differentiators (Add Value, Not Required for Milestone)

#### Batched JMAP Label Queries

| Aspect | Detail |
|--------|--------|
| **Value** | Instead of N sequential `Email/query` calls (one per label), send all queries in a single JMAP request as a batched `methodCalls` array. Reduces poll latency from O(N) round-trips to 1. With 5 categories, this is 5 → 1 round-trip. |
| **Complexity** | LOW — `JMAPClient.call()` already accepts a list of method calls. The change is in `_collect_triaged()`: build one big `methodCalls` list, send once, process responses. |
| **Depends on** | Feature 3 (label-based scanning confirms the query pattern; worth optimizing once pattern is proven) |

#### Human Test Coverage for Re-Triage

| Aspect | Detail |
|--------|--------|
| **Value** | Re-triage is the highest-risk new behavior (it moves contacts and re-files emails). A human integration test that: adds sender A to Paper Trail, then applies @ToJail, verifies contact moved and emails refiled — would catch real-world edge cases that unit tests miss (CardDAV ETag conflicts, Fastmail group update atomicity). |
| **Complexity** | MEDIUM — needs setup/teardown to avoid polluting real contact data |
| **Depends on** | Feature 4 (can't test until re-triage is built) |

#### `add_to_inbox` Inheritance via Parent Chain

| Aspect | Detail |
|--------|--------|
| **Value** | If Person is a child of Imbox, Person emails should appear in Inbox (because Imbox has `add_to_inbox: true`). Without this, users would need to redundantly set `add_to_inbox: true` on every child of an inbox-bound parent. |
| **Complexity** | LOW — already part of the parent chain walking in Feature 2; just extend the resolution logic to carry `add_to_inbox` through |
| **Depends on** | Feature 1 (`add_to_inbox` field must exist first) + Feature 2 (parent chain walking) |
| **Note** | Marked as open question in the todo. Recommended: inherit — it's the intuitively correct behavior and trivial to implement during Feature 2's chain-walking code. |

---

### Anti-Features (Do Not Build in v1.2)

| Anti-Feature | Why Tempting | Why Avoid | What to Do Instead |
|--------------|-------------|-----------|-------------------|
| Sweep workflow (re-label archived emails by contact group) | Elegant self-healing for accidental archive-swipe label removal | Far-future architecture goal (separate workflow engine, expensive scan). The contact-group-as-source-of-truth insight is sound but the implementation scope is a different milestone entirely. | Defer to v1.3+. Capture in todo (already exists as `2026-02-26-sweep-workflow`). |
| JMAP Contacts migration (replace CardDAV) | RFC 9610 is live on Fastmail; JSON native, single protocol | v1.2 feature scope is already defined. CardDAV works reliably. Migration is a dedicated milestone, not a side feature. | Defer to a dedicated milestone. Research already captured in `2026-02-26-migrate-to-jmap-contacts-api.md`. |
| Programmatic sieve rule creation | Eliminates manual sieve setup step | Fastmail sieve API availability is unverified for writes; scope is large. Not blocking v1.2 features. | Defer to same future milestone as JMAP Contacts migration. |
| Confirmation mechanism for re-triage | "Force re-triage" special label to prevent accidental group moves | The triage label itself IS the explicit user action. Adding a confirmation step adds friction to a deliberate operation. `@MailroomWarning` provides sufficient auditability. | Ship "just do it" behavior with `@MailroomWarning` notification. |
| Re-triage history / undo log | Track previous group for rollback | Single-user tool; Fastmail's own email history is the audit trail. An in-service log adds complexity for no real value. | `@MailroomWarning` + structured JSON log provides sufficient history. |
| Scan ALL mailboxes for triage labels | Comprehensive label detection | Already unnecessary: JMAP label mailboxes ARE the scope. Querying `inMailbox: <label_id>` returns emails with that label across ALL mailboxes — nothing more is needed. | Already handled by label-based scanning (Feature 3). |
| Nested mailbox hierarchy for child categories | Billboard under Paper Trail in Fastmail UI | Fastmail nesting is cosmetic; additive labels (Feature 2) already make emails appear in both parent and child views. Flat namespace is simpler and already works. | Use additive labels instead. Flat mailbox namespace. |

---

## Feature Dependencies

```
[Tech Debt Cleanup] (Feature 5)
    |
    +---> unblocks Features 1 + 2
    |     (public resolved_categories property; clean slate before config changes)
    |
    +---> INDEPENDENT of Features 3 + 4 (can ship in parallel)

[Feature 1: add_to_inbox Flag]
    |
    +---> required by Feature 2 (open question: add_to_inbox inheritance)
    |     (build together in same phase or Feature 1 first)
    |
    +---> affects Feature 3 (sweeping Inbox vs destination mailbox needs correct flag)

[Feature 2: Additive Parent Labels]
    |
    +---> builds on Feature 1 (parent chain walking already needed for add_to_inbox)
    |
    +---> affects Feature 3 (child categories now have own labels to scan)
    |
    +---> affects setup provisioner + sieve guidance (own resources per child)

[Feature 3: Label-Based Scanning]
    |
    +---> required by Feature 4 (re-triage needs correct sweep scope)
    |
    +---> enables the core value: triage label works wherever the email lives

[Feature 4: Re-Triage]
    |
    +---> depends on Feature 3 (old-label sweep needs label-based queries)
    |
    +---> adds CardDAV group removal capability (new method on CardDAVClient)
    |
    +---> enhances existing @MailroomWarning infrastructure (already exists in screener.py)
```

### Critical Ordering Constraints

1. **Tech debt before feature work** — `resolved_categories` property needed by Feature 2; clean test fixtures matter
2. **Feature 1 before Feature 2** — additive label chain walking must carry `add_to_inbox` through; cleanest if done together
3. **Feature 3 before Feature 4** — re-triage's old-label sweep relies on label-based queries
4. **Features 1+2 before Feature 3** — scanning must handle new child categories that have own labels (not shared with parent)
5. **Features 1+2 can overlap with Feature 3** — config changes and scanning are in different modules

**Recommended build order:**
- Phase A: Tech debt cleanup (5)
- Phase B: `add_to_inbox` flag + additive parent labels (1 + 2 together — both touch `resolve_categories()`)
- Phase C: Label-based scanning (3)
- Phase D: Re-triage (4)

---

## MVP Definition

### Must Ship (defines v1.2)

- [x] **Tech debt cleanup (5)** — clears v1.1 audit items before new work
- [x] **`add_to_inbox` flag (1)** — makes Imbox config correct; unblocks child category independence
- [x] **Additive parent labels (2)** — makes parent/child semantics useful and correct
- [x] **Label-based scanning (3)** — makes triage work wherever the email lives; required for re-triage
- [x] **Re-triage / group reassignment (4)** — completes the "user can change their mind" workflow

### Add After Validation (v1.2.x)

- Batched JMAP label queries — optimization once correctness is proven
- Human test for re-triage — high-confidence validation of the most complex new behavior
- `add_to_inbox` inheritance through parent chain — if not included in Feature 2 phase

### Future Consideration (v1.3+)

- Sweep workflow (self-healing label integrity from accidental archive-swipe)
- JMAP Contacts migration (replace CardDAV with RFC 9610)
- Programmatic sieve rule creation

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Tech debt cleanup (5) | LOW (process) | LOW | P1 — enables clean feature work |
| `add_to_inbox` flag (1) | HIGH — correct Imbox semantics | LOW-MEDIUM | P1 — config correctness |
| Additive parent labels (2) | HIGH — makes parent/child useful | MEDIUM | P1 — core pipeline change |
| Label-based scanning (3) | HIGH — triage works anywhere | LOW | P1 — fixes silent partial-success bug |
| Re-triage (4) | HIGH — intentional group change | MEDIUM | P1 — closes current UX dead-end |
| Batched JMAP queries | MEDIUM — latency reduction | LOW | P2 — optimization |
| Human test for re-triage | MEDIUM — confidence | MEDIUM | P2 — add after feature ships |
| Sweep workflow | HIGH (long term) | HIGH | P3 — different milestone |

---

## Impact on Existing Code

| File | Feature 1 Impact | Feature 2 Impact | Feature 3 Impact | Feature 4 Impact |
|------|-----------------|-----------------|-----------------|-----------------|
| `core/config.py` | Add `add_to_inbox` field + validation | Simplify second-pass resolution; add `parent_labels` to `ResolvedCategory` | None | None |
| `workflows/screener.py` | `_get_destination_mailbox_ids()` includes Inbox when flag set | Add parent-label application step in `_process_sender()` | Replace Screener sweep query with label-based query | Replace error-on-different-group with reassignment logic |
| `clients/jmap.py` | None | None | None | Possible: new `add_mailbox_labels()` helper if parent-label apply needs own method |
| `clients/carddav.py` | None | None | None | New: `remove_from_group(contact_uid, group_name)` |
| `setup/provisioner.py` | Update default Imbox provisioning | Each child category provisions own mailbox + group | None | None |
| `setup/sieve_guidance.py` | Access via public property (tech debt) | Child rules generate parent-label actions | None | None |
| `config.yaml` | `imbox: add_to_inbox: true` | Child categories now show own mailboxes | None | None |
| `tests/conftest.py` | Tech debt cleanup | None | None | None |

### What Does NOT Change

- `ScreenerWorkflow.poll()` orchestration structure
- EventSource push + polling fallback (`eventsource.py`, `__main__.py`)
- JMAP session/connect/call infrastructure
- CardDAV core operations (search, create_contact, upsert_contact)
- Health endpoint
- Helm chart, Docker, deployment
- Human tests 1-16 (poll() behavior unchanged for non-parent-child, non-reassignment cases)

---

## Open Questions to Resolve During Phase Planning

1. **Does `add_to_inbox` inherit through parent chain?** Recommendation: YES. If Imbox has `add_to_inbox: true` and Person is a child of Imbox, Person emails should also appear in Inbox. Trivial to implement during Feature 2's chain-walking code.

2. **Scan scope: all label mailboxes or configurable subset?** The JMAP query pattern (`inMailbox: <label_id>`) naturally scopes to emails with that label. "All label mailboxes" is the correct default — no further configuration needed. No opt-in/opt-out mechanism required.

3. **How does re-triage find the old category label when the old category is no longer in config?** If the old group name doesn't map to any current `ResolvedCategory`, skip the old-label sweep, log a warning, and still complete the contact group move. Old emails are left in place with stale labels — user can clean up manually.

4. **Should re-triage sweep ALL emails with old label, or only from the Screener?** With Feature 3's label-based scanning: sweep emails with old label anywhere (`inMailbox: <old_label_id>, from: <sender>`). This is the correct behavior — move all re-categorized sender's emails to the new destination.

---

## Sources

- `src/mailroom/core/config.py` — `TriageCategory`, `ResolvedCategory`, `resolve_categories()`, current parent inheritance logic (HIGH confidence — live codebase)
- `src/mailroom/workflows/screener.py` — `_process_sender()`, `_collect_triaged()`, `_check_already_grouped()`, `_get_destination_mailbox_ids()` (HIGH confidence — live codebase)
- `src/mailroom/clients/jmap.py` — `query_emails()`, `batch_move_emails()`, `call()` (HIGH confidence — live codebase)
- `.planning/todos/pending/2026-03-02-separate-inbox-flag-from-destination-mailbox-in-category-config.md` (HIGH confidence — explicit design spec)
- `.planning/todos/pending/2026-03-02-change-parent-inheritance-to-additive-label-propagation.md` (HIGH confidence — explicit design spec)
- `.planning/todos/pending/2026-02-28-allow-contact-group-reassignment-via-triage-label.md` (HIGH confidence — explicit design spec)
- `.planning/todos/pending/2026-02-25-scan-for-action-labels-beyond-screener-mailbox.md` (HIGH confidence — design intent)
- `.planning/todos/pending/2026-03-02-resolve-v1-1-tech-debt-carry-forward-in-v1-2.md` (HIGH confidence — audit findings)
- `.planning/PROJECT.md` — v1.2 milestone spec (HIGH confidence)
- RFC 8621 Section 2 — JMAP `Email/query` filter spec (HIGH confidence — already proven in codebase)

---
*Feature research for: v1.2 Triage Pipeline v2*
*Researched: 2026-03-02*
