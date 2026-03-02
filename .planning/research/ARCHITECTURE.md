# Architecture Research

**Domain:** Triage pipeline evolution — inbox flag separation, additive parent labels, label-based scanning, re-triage
**Researched:** 2026-03-02
**Confidence:** HIGH (full codebase inspected: config.py, screener.py, jmap.py, carddav.py, __main__.py, provisioner.py, v1.1 architecture research reviewed)

---

## Current Architecture (As-Is)

```
                    +----------------------------------------------------+
                    |                  __main__.py                        |
                    |                                                     |
                    |   main()                                            |
                    |     settings = MailroomSettings()                   |
                    |     mailbox_ids = resolve_mailboxes()               |
                    |     carddav.validate_groups()                       |
                    |     workflow = ScreenerWorkflow(...)                 |
                    |     _start_health_server()                          |
                    |     sse_thread.start() [daemon]                     |
                    |                                                     |
                    |     while not shutdown:                              |
                    |       event_queue.get(timeout=poll_interval)        |
                    |       drain_queue() + debounce wait                 |
                    |       workflow.poll()    <-- SINGLE WORKFLOW        |
                    +----------------------------------------------------+
                              |              |              |
               +--------------+              |              +--------------+
               |                             |                             |
   +-----------v---------+   +--------------v-------------+   +-----------v-----------+
   |   JMAPClient         |   |   EventSourceListener      |   |   CardDAVClient        |
   |   clients/jmap.py    |   |   eventsource.py           |   |   clients/carddav.py   |
   |                      |   |                            |   |                        |
   |   call()             |   |   sse_listener() fn        |   |   connect()            |
   |   resolve_mailboxes()|   |   drain_queue() fn         |   |   validate_groups()    |
   |   query_emails()     |   |   queue.Queue -> main      |   |   search_by_email()    |
   |   get_email_senders()|   +----------------------------+   |   create_contact()     |
   |   batch_move_emails()|                |                   |   add_to_group()       |
   |   remove_label()     |                v                   |   upsert_contact()     |
   |   create_mailbox()   |   Fastmail EventSource             |   check_membership()   |
   +----------------------+   api.fastmail.com/jmap/event/     |   create_group()       |
               |                                               +-----------------------+
               v                                                           |
   Fastmail JMAP API                                            Fastmail CardDAV API
   api.fastmail.com                                             carddav.fastmail.com
```

### Current ScreenerWorkflow.poll() Steps

```
1. _collect_triaged()
   - For each triage label → query_emails(label_mailbox_id) [SEQUENTIAL CALLS]
   - get_email_senders(email_ids)
   - Filter out @MailroomError emails via Email/get

2. _detect_conflicts()
   - Same sender + different labels → conflicted

3. _apply_error_label() on conflicted senders

4. _process_sender() for each clean sender:
   a. _check_already_grouped()  → CardDAV
   b. carddav.upsert_contact()  → CardDAV
   c. query_emails(screener_id, sender=sender)  [SCREENER ONLY]
   d. batch_move_emails(screener_emails, screener_id, dest_ids)
   e. remove_label(email_id, label_id)
```

### Key Constraints in Current Code

1. **Scan scope is Screener-only.** `_process_sender()` sweeps `screener_id` regardless of label. If email is already out of Screener, it is not swept.
2. **Inbox special case is implicit.** `_get_destination_mailbox_ids()` checks `destination_mailbox == "Inbox"`. No flag.
3. **Parent inheritance overwrites.** `resolve_categories()` second pass applies parent's `contact_group` and `destination_mailbox` to child if child did not specify them. Child's label is always its own.
4. **Sequential label queries.** Each triage label is queried in a separate `Email/query` call inside `_collect_triaged()`.
5. **Already-grouped check catches re-triage.** `check_membership()` iterates all groups and returns if contact is in a different one. This triggers `@MailroomError` — no re-triage happens.

---

## Feature Integration Analysis

### Feature 1: Separate `add_to_inbox` Flag from `destination_mailbox`

**Current code path:**

```python
# config.py — TriageCategory
destination_mailbox: str | None = None   # e.g. "Inbox" for Imbox category

# screener.py — _get_destination_mailbox_ids()
category = self._settings.label_to_category_mapping[label_name]
destination_mailbox = category.destination_mailbox
return [self._mailbox_ids[destination_mailbox]]  # always [dest_id], no inbox
```

The Imbox special case is actually handled by the DEFAULT config setting `destination_mailbox="Inbox"` — the Inbox IS the destination. Looking at the sweep logic: `batch_move_emails(sender_emails, screener_id, [inbox_id])` where `add_ids` comes from `_get_destination_mailbox_ids()`. So for Imbox, the destination mailbox is "Inbox" and the email is moved there directly. There is NO separate inbox re-labeling step in the current v1.1 code. The initial design intent from v1.0 was that swept Imbox emails get the Inbox label added; this was implemented by using "Inbox" as the destination.

**What separation means:**
- `destination_mailbox`: where the email physically lives (e.g. "Feed", "Paper Trail")
- `add_to_inbox` flag: whether to ALSO add the Inbox label (so email appears in Inbox too)
- Use case: a category that lives in "Paper Trail" but should ALSO appear in Inbox

**Changes needed:**

| Component | File | Change |
|-----------|------|--------|
| `TriageCategory` | `core/config.py` | Add `add_to_inbox: bool = False` field |
| `ResolvedCategory` | `core/config.py` | Add `add_to_inbox: bool` field |
| `_default_categories()` | `core/config.py` | Set `add_to_inbox=True` on Imbox category (since Imbox sweeps to Inbox) |
| `resolve_categories()` | `core/config.py` | Propagate/resolve `add_to_inbox` (does it inherit? — open question) |
| `_get_destination_mailbox_ids()` | `workflows/screener.py` | If `add_to_inbox`, include inbox_id in returned list |
| `required_mailboxes` | `core/config.py` | "Inbox" must always be in required list if any category has `add_to_inbox=True` |

**Default config migration:** The default `Imbox` category changes from `destination_mailbox="Inbox"` to `destination_mailbox="Imbox" (or keep "Inbox"), add_to_inbox=True`. This is a semantic clarification — the actual behavior for existing users is unchanged since the default categories are hardcoded.

**Open question on inheritance:** If a parent category has `add_to_inbox=True`, should children inherit it? Recommendation: NO. `add_to_inbox` is an opt-in signal for specific categories. Children should default to `False` unless explicitly set. This avoids accidental inbox flooding for subcategories.

**Integration point:** `_get_destination_mailbox_ids()` in `screener.py` is the only call site. Change is localized. The `mailbox_ids` dict passed to `ScreenerWorkflow` must include "Inbox" whenever any category has `add_to_inbox=True`.

---

### Feature 2: Additive Parent Label Propagation

**Current behavior (parent inheritance):**

```python
# resolve_categories() second pass (config.py lines 230-255)
# Child INHERITS parent's contact_group and destination_mailbox (unless child specifies own)
# Example: Person category (parent=Imbox) gets contact_group="Imbox", destination_mailbox="Inbox"
```

**Proposed additive behavior:**
- Child keeps its own `contact_group` and `destination_mailbox` (independent category)
- Child ADDS parent's labels to the sweep targets (emails are moved to BOTH child and parent destinations)
- More precisely: when sweeping, emails get ALL labels from child + parent chain

**Example:**

```
Imbox (parent)  → label: @ToImbox,  contact_group: Imbox,     destination_mailbox: Inbox
Person (child)  → label: @ToPerson, contact_group: Person,    destination_mailbox: Person
                    additive: also applies Imbox's destination behavior
```

With additive propagation: @ToPerson triage would move emails to Person mailbox AND add Inbox label (because Imbox parent has `add_to_inbox=True`).

**This interacts with `add_to_inbox`:** A child whose parent has `add_to_inbox=True` should propagate that flag. This is the main value of additive propagation — the Inbox behavior propagates down the chain without the child needing to explicitly set it.

**Changes needed:**

| Component | File | Change |
|-----------|------|--------|
| `resolve_categories()` | `core/config.py` | Second pass: instead of replacing child fields with parent's, COLLECT parent chain's labels. Store as `parent_labels: list[str]` on ResolvedCategory — the list of destination mailboxes/flags from all ancestors |
| `ResolvedCategory` | `core/config.py` | Add `add_to_inbox: bool` derived from own flag OR any ancestor with `add_to_inbox=True` |
| `_get_destination_mailbox_ids()` | `workflows/screener.py` | Now must be aware that add_to_inbox can come from parent chain |

**Concrete implementation recommendation:**

Do NOT add a `parent_labels` list to `ResolvedCategory`. Instead:
- Walk the parent chain during resolution
- Compute a single derived `add_to_inbox: bool` (True if self OR any ancestor has it)
- `contact_group` and `destination_mailbox` remain child's OWN values (no inheritance)
- This is the minimal change that captures the meaningful behavior

The current "inheritance" of `contact_group` and `destination_mailbox` is removed. Children ALWAYS use their own values for these. The only thing that propagates is the `add_to_inbox` flag (upward: if any ancestor has it, child gets it).

**Impact on existing default config:**
- `Person` category currently inherits `contact_group="Imbox"` and `destination_mailbox="Inbox"` from parent Imbox
- With additive semantics: Person gets its OWN `contact_group="Person"`, `destination_mailbox="Person"` (derived from name), plus `add_to_inbox=True` propagated from Imbox parent
- This is a BEHAVIORAL CHANGE for existing Person triage — contacts go to Person group (not Imbox group) and emails go to Person mailbox (not Inbox). If user wants Inbox behavior, it comes from `add_to_inbox=True` propagating.
- This requires updating `_default_categories()` to reflect the new semantics explicitly

---

### Feature 3: Label-Based Scanning (JMAP Batched Queries)

**Current problem:**

```python
# screener.py _collect_triaged() — N sequential HTTP calls (one per label)
for label_name in self._settings.triage_labels:
    label_id = self._mailbox_ids[label_name]
    email_ids = self._jmap.query_emails(label_id)  # HTTP round-trip per label
```

With 5 default categories = 5 sequential HTTP calls per poll cycle.

**Proposed solution: JMAP method call batching**

JMAP supports multiple method calls in a single HTTP request via `methodCalls` array. The `call()` method already accepts a list of method call triples. A single request can include N `Email/query` calls, one per label mailbox.

**New JMAPClient method:**

```python
def batch_query_emails(
    self,
    mailbox_ids: list[str],
    limit: int = 100,
) -> dict[str, list[str]]:
    """Query email IDs across multiple mailboxes in a single JMAP request.

    Args:
        mailbox_ids: List of mailbox IDs to query.
        limit: Max emails per mailbox per page.

    Returns:
        Dict mapping mailbox_id -> list of email IDs.
    """
    method_calls = [
        [
            "Email/query",
            {
                "accountId": self.account_id,
                "filter": {"inMailbox": mb_id},
                "limit": limit,
            },
            f"q{i}",
        ]
        for i, mb_id in enumerate(mailbox_ids)
    ]
    responses = self.call(method_calls)
    result: dict[str, list[str]] = {}
    for i, mb_id in enumerate(mailbox_ids):
        data = responses[i][1]
        result[mb_id] = data.get("ids", [])
    return result
```

**Pagination note:** If any label mailbox has more than `limit` emails, the batched query returns only the first page. The current `query_emails()` handles pagination automatically. `batch_query_emails()` should also handle pagination, but in practice a triage label mailbox should never have >100 emails (user is expected to process them). Start without pagination in batch query; fall back to individual `query_emails()` if needed.

**Integration in `_collect_triaged()`:**

```python
# BEFORE: N sequential calls
for label_name in self._settings.triage_labels:
    label_id = self._mailbox_ids[label_name]
    email_ids = self._jmap.query_emails(label_id)

# AFTER: 1 batched call
label_mailbox_ids = [self._mailbox_ids[ln] for ln in self._settings.triage_labels]
results = self._jmap.batch_query_emails(label_mailbox_ids)
# then iterate results dict
```

**Also: scan scope is now ALL label mailboxes, not just Screener emails**

The current `_process_sender()` sweeps from Screener only:
```python
screener_id = self._mailbox_ids[self._settings.triage.screener_mailbox]
sender_emails = self._jmap.query_emails(screener_id, sender=sender)
```

With label-based scanning, triage labels can appear on emails in ANY mailbox. The sweep should query the sender's emails across all relevant mailboxes, not just Screener.

**Recommended sweep scope change:** Instead of `query_emails(screener_id, sender=sender)`, query by sender WITHOUT mailbox filter, then filter to only emails that are NOT already in the correct destination. This is broader but necessary for the re-triage use case.

Alternatively: sweep from BOTH screener AND any mailbox where the email currently lives. The key insight from PROJECT.md: "Pre-v1.2 research: JMAP labels are mailboxes — scanning for triage labels by querying label mailbox IDs directly (batched) is fast and eliminates Screener-only limitation." This confirms the scan is by label mailbox ID (which any email can be in), not by Screener location.

**What this means for `_collect_triaged()`:** The change is ALREADY implicit. Querying a label mailbox ID returns ALL emails with that label, regardless of which other mailboxes they're also in. So the scan-beyond-Screener for COLLECTION is achieved simply by querying label IDs directly (which is already how `query_emails(label_id)` works). The Screener restriction was only in the SWEEP step.

---

### Feature 4: Re-Triage (Contact Group Reassignment)

**Current behavior:**

```python
# screener.py _check_already_grouped()
existing_group = self._check_already_grouped(sender, group_name)
if existing_group is not None:
    # Sender in DIFFERENT group → apply @MailroomError, STOP
    self._apply_error_label(sender, emails)
    return
```

Re-triage means: when a sender is in group A but the user applies label B (for group B), the service should:
1. Remove sender from group A
2. Add sender to group B
3. Re-file existing emails from their current location to the new destination
4. Apply `@MailroomWarning` (not `@MailroomError`) to signal this happened

**Changes needed in CardDAVClient:**

```python
def remove_from_group(
    self,
    group_name: str,
    contact_uid: str,
    max_retries: int = 3,
) -> str:
    """Remove a contact from a group by modifying the group's vCard.

    Fetches group vCard, removes X-ADDRESSBOOKSERVER-MEMBER entry,
    PUTs back with If-Match. Retries on 412 Precondition Failed.
    """
```

This follows the same ETag-retry pattern as `add_to_group()`. The only difference is removing the member URN instead of appending it.

**Changes needed in ScreenerWorkflow:**

`_process_sender()` gains a re-triage branch:

```python
# BEFORE: already-grouped in wrong group → error, return
if existing_group is not None:
    self._apply_error_label(sender, emails)
    return

# AFTER: already-grouped in wrong group → re-triage
if existing_group is not None:
    self._retriage_sender(sender, emails, existing_group, category)
    return
```

New `_retriage_sender()` method:

```python
def _retriage_sender(
    self,
    sender: str,
    emails: list[tuple[str, str]],
    old_group: str,
    new_category: ResolvedCategory,
) -> None:
    """Move sender from old_group to new_category's group.

    Steps:
    1. Remove contact from old_group (CardDAV)
    2. Add contact to new_category.contact_group (CardDAV)
    3. Find all emails from sender (all mailboxes)
    4. Re-file emails to new destination
    5. Apply @MailroomWarning to triggering emails
    6. Remove triage label — LAST STEP
    """
```

**Finding all sender emails for re-filing:**

```python
# Query sender's emails without mailbox filter
# JMAP Email/query with filter: {"from": sender} and no inMailbox constraint
sender_all_emails = self._jmap.query_emails_by_sender(sender)
# Then move from wherever they are to new destination
```

This requires a new JMAPClient method or extending `query_emails()` to not require a mailbox_id.

**Current `query_emails()` signature:**

```python
def query_emails(self, mailbox_id: str, sender: str | None = None, ...) -> list[str]:
    email_filter: dict = {"inMailbox": mailbox_id}
```

The `mailbox_id` is required. To query by sender across all mailboxes, need to make it optional:

```python
def query_emails(
    self,
    mailbox_id: str | None = None,
    sender: str | None = None,
    ...
) -> list[str]:
    email_filter: dict = {}
    if mailbox_id is not None:
        email_filter["inMailbox"] = mailbox_id
    if sender is not None:
        email_filter["from"] = sender
```

**Re-filing "from wherever they are":**

Current `batch_move_emails(email_ids, remove_mailbox_id, add_mailbox_ids)` removes one specific mailbox and adds destination. For re-triage, the "remove" source is not a single mailbox — emails could be in Feed, Paper Trail, Screener, etc.

Options:
1. Query each email's current mailboxIds, then construct per-email patches
2. Don't remove old destination — just add new destination label (additive label approach)
3. Remove ALL non-system mailboxes, add new destination (destructive, risky)

**Recommendation: Option 1** — query current mailbox membership for affected emails, remove old category mailbox(es), add new destination. This requires an `Email/get` call to fetch `mailboxIds` for each sender's email, then per-email patches. This is already done in `_collect_triaged()` for error filtering. Reuse that pattern.

Alternatively for v1.2: only re-file the TRIGGERING emails (the ones with the new triage label), not ALL sender emails. Full re-filing of historical emails is a scope expansion that can be a future phase. Start with: (1) re-triage the contact group, (2) sweep emails that are explicitly labeled with the new triage label, (3) apply warning. Historical re-filing left for later.

---

## Proposed Architecture (To-Be)

```
                    +----------------------------------------------------+
                    |                  __main__.py (unchanged)            |
                    |                                                     |
                    |   while not shutdown:                               |
                    |     event_queue.get() / timeout                     |
                    |     workflow.poll()                                 |
                    +----------------------------------------------------+
                              |
                    +---------v---------+
                    |  ScreenerWorkflow  |
                    |  (modified)        |
                    |                    |
                    |  poll()            |
                    |  _collect_triaged()  ← batched label queries        |
                    |  _detect_conflicts()                                |
                    |  _process_sender()                                  |
                    |    ├─ _check_already_grouped()                      |
                    |    ├─ _retriage_sender()        [NEW]               |
                    |    ├─ carddav.upsert_contact()                      |
                    |    ├─ _sweep_sender_emails()    [modified scope]    |
                    |    └─ _apply_warning_label()                        |
                    +-------------------+--------------------+
                              |                              |
              +---------------v-------+       +--------------v----------+
              |   JMAPClient           |       |   CardDAVClient          |
              |   (modified)           |       |   (modified)             |
              |                        |       |                          |
              |  batch_query_emails()  |       |  remove_from_group()     |
              |    [NEW]               |       |    [NEW]                 |
              |  query_emails()        |       |  add_to_group()          |
              |    [mailbox_id opt.]   |       |  upsert_contact()        |
              |  batch_move_emails()   |       |  check_membership()      |
              +------------------------+       +--------------------------+
```

### Component Boundaries

| Component | File | Status | What Changes |
|-----------|------|--------|--------------|
| `TriageCategory` | `core/config.py` | Modified | Add `add_to_inbox: bool = False` field |
| `ResolvedCategory` | `core/config.py` | Modified | Add `add_to_inbox: bool` field |
| `resolve_categories()` | `core/config.py` | Modified | Remove field-inheritance; propagate `add_to_inbox` from parent chain; children keep own contact_group/destination_mailbox |
| `_default_categories()` | `core/config.py` | Modified | Imbox gets `add_to_inbox=True`; Person gets own contact_group/destination, not inherited |
| `ScreenerWorkflow._collect_triaged()` | `workflows/screener.py` | Modified | Use `batch_query_emails()` instead of sequential `query_emails()` per label |
| `ScreenerWorkflow._process_sender()` | `workflows/screener.py` | Modified | Re-triage branch instead of error-on-wrong-group |
| `ScreenerWorkflow._get_destination_mailbox_ids()` | `workflows/screener.py` | Modified | Return inbox_id in addition to dest_id when `add_to_inbox=True` |
| `ScreenerWorkflow._retriage_sender()` | `workflows/screener.py` | NEW | Remove from old group, add to new group, sweep/warn |
| `JMAPClient.batch_query_emails()` | `clients/jmap.py` | NEW | Single JMAP request for N label mailboxes |
| `JMAPClient.query_emails()` | `clients/jmap.py` | Modified | Make `mailbox_id` optional for sender-only queries |
| `CardDAVClient.remove_from_group()` | `clients/carddav.py` | NEW | ETag-safe group member removal |
| `__main__.py` | `__main__.py` | Unchanged | No changes needed |
| `eventsource.py` | `eventsource.py` | Unchanged | No changes needed |
| `setup/provisioner.py` | `setup/provisioner.py` | Unchanged | No changes needed |
| `setup/sieve_guidance.py` | `setup/sieve_guidance.py` | Possibly modified | Update sieve output if category semantics change |

---

## Data Flow Changes

### Triage Collection (Before vs After)

**Before — 5 sequential HTTP calls:**
```
poll() start
  → Email/query {inMailbox: "@ToImbox_id"}          [HTTP 1]
  → Email/query {inMailbox: "@ToFeed_id"}            [HTTP 2]
  → Email/query {inMailbox: "@ToPaperTrail_id"}      [HTTP 3]
  → Email/query {inMailbox: "@ToJail_id"}            [HTTP 4]
  → Email/query {inMailbox: "@ToPerson_id"}          [HTTP 5]
  → Email/get {ids: all_email_ids}                   [HTTP 6 — filter errors]
```

**After — 1 batched HTTP call:**
```
poll() start
  → JMAP batch: [Email/query q0, q1, q2, q3, q4]   [HTTP 1 — all labels]
  → Email/get {ids: all_email_ids}                   [HTTP 2 — filter errors + get senders]
```

The `get_email_senders()` call (currently separate) can also be merged into the same batch as the error-filter `Email/get`. Net reduction: 6 HTTP calls → 2-3 HTTP calls per poll cycle.

### Re-Triage Data Flow

```
User applies @ToPerson label to email from alice@corp.com
Alice is currently in "Feed" group

poll() → _collect_triaged()
  → batch_query_emails() finds alice@corp.com in @ToPerson mailbox
  → email_id: "em123", label: "@ToPerson"

_detect_conflicts() → clean (single label for this sender)

_process_sender(alice@corp.com, [("em123", "@ToPerson")], ...)
  → label: @ToPerson, category: Person
  → group_name: "Person"

_check_already_grouped(alice, "Person")
  → check_membership(alice_uid, exclude_group="Person")
  → returns "Feed" (she's in Feed)

existing_group = "Feed" → NOT None

_retriage_sender(alice, emails, old_group="Feed", new_category=Person)
  Step 1: carddav.remove_from_group("Feed", alice_uid)
  Step 2: carddav.add_to_group("Person", alice_uid)
  Step 3: jmap.query_emails(sender=alice@corp.com) [scope: triggering emails or all]
  Step 4: batch_move_emails(emails, old_dest_id, new_dest_ids)
  Step 5: _apply_warning_label(alice, email_ids)
  Step 6: remove_label(email_id, person_label_id)  ← LAST

log: re_triaged, sender=alice, old_group=Feed, new_group=Person
```

### Additive Label / `add_to_inbox` Data Flow

```
Config: Person category, parent=Imbox
Imbox has add_to_inbox=True
resolve_categories() propagates: Person.add_to_inbox = True (inherited from parent)

_process_sender(bob, ..., category=Person)
  → _get_destination_mailbox_ids("@ToPerson")
  → category.add_to_inbox is True
  → returns [person_mailbox_id, inbox_id]  ← both added

batch_move_emails(sender_emails, screener_id, [person_mailbox_id, inbox_id])
  → Bob's emails go to Person mailbox AND appear in Inbox
```

---

## Suggested Build Order

Dependencies between features determine the build order. `add_to_inbox` is a pure config change. Label scanning is a JMAPClient and workflow change. Additive parent propagation changes config semantics. Re-triage changes workflow and CardDAV.

```
Phase A: Config — inbox flag + additive parent propagation
    |
    Rationale: Foundation. All other features read from config.
    Changes only config.py and its tests.
    Existing tests must pass (backward compat gate).
    |
    v
Phase B: JMAPClient — batch_query_emails + optional mailbox_id on query_emails
    |
    Rationale: New client capabilities needed by workflow changes.
    Isolated to jmap.py. No workflow changes yet.
    Can be tested independently with unit tests.
    |
    v
Phase C: CardDAVClient — remove_from_group
    |
    Rationale: New client capability needed by re-triage.
    Isolated to carddav.py. ETag-retry pattern is existing art.
    |
    v
Phase D: ScreenerWorkflow — label scanning + add_to_inbox behavior
    |
    Rationale: Wire Phase A config + Phase B batch queries into workflow.
    _collect_triaged() uses batched queries.
    _get_destination_mailbox_ids() uses add_to_inbox flag.
    No re-triage yet — still errors on wrong group (safe).
    |
    v
Phase E: ScreenerWorkflow — re-triage
    |
    Rationale: Build on Phase C (remove_from_group) and Phase D (sweep scope).
    _process_sender() re-triage branch instead of error.
    _retriage_sender() new method.
    Highest behavioral risk — phase separately for focused testing.
    |
    v
Phase F: Tech debt (v1.1 carry-forward)
    |
    Rationale: Clean up after feature work settles.
    Phase 09.1.1 VERIFICATION.md, sieve_guidance private access,
    conftest stale env vars, test_13 polling interval issue.
```

**Why this order:**
- Config changes first because ScreenerWorkflow and JMAPClient read from it
- Client methods before workflow so the workflow can assume they exist
- Label scanning before re-triage because re-triage needs broader sweep scope
- Re-triage last because it's the highest behavioral risk and most complex
- Tech debt last so it does not intermingle with feature changes

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Inheriting `contact_group` and `destination_mailbox` from Parent

**What people do:** Keep the current second-pass inheritance that copies parent's `contact_group` and `destination_mailbox` to child.
**Why it's wrong:** It prevents meaningful child categories. If Person inherits Imbox's contact_group and destination_mailbox, Person IS Imbox. The parent relationship becomes meaningless except as a label grouping.
**Do this instead:** Children always have their own `contact_group` and `destination_mailbox` (derived from their name if not specified). The ONLY thing that propagates from parent is `add_to_inbox`.

### Anti-Pattern 2: Re-Filing All Historical Emails During Re-Triage

**What people do:** When re-triaging Alice from Feed to Person, query ALL of Alice's emails ever received and move them all to the new destination.
**Why it's wrong:** A sender might have thousands of historical emails. Fetching and moving all of them is O(n) in email count, can hit JMAP batch limits, takes minutes, and is a destructive operation the user may not want for old emails.
**Do this instead:** Re-triage only the emails that triggered the re-triage (emails in the new triage label mailbox). Apply `@MailroomWarning` so the user knows the group changed. Sieve rules handle future routing. Historical emails can be cleaned up manually if desired.

### Anti-Pattern 3: Making `batch_query_emails` Handle Pagination Internally

**What people do:** Add full pagination logic inside `batch_query_emails()` by looping with increasing position offsets for each mailbox.
**Why it's wrong:** Pagination in a batch call requires a second HTTP round-trip anyway (one per page per mailbox). The complexity is not worth it for triage label mailboxes, which should never have > 100 pending emails.
**Do this instead:** `batch_query_emails()` returns first page only. If any mailbox returns `total > len(ids)`, log a warning and process what was returned. The next poll cycle will catch remaining emails.

### Anti-Pattern 4: Removing @MailroomError Entirely for Wrong-Group Detection

**What people do:** Replace the existing `_check_already_grouped()` → `@MailroomError` path entirely with re-triage.
**Why it's wrong:** Re-triage is a destructive operation (changes group membership). If the user did NOT intend to re-triage (e.g., accidentally applied the wrong label), silent re-triage is worse than an error label. The error label is recoverable; a group change is less visible.
**Do this instead:** Re-triage and apply `@MailroomWarning`. The warning label signals the group changed. The user can see in the warning label mailbox what happened and verify. This is less disruptive than `@MailroomError` (which blocks processing) but more visible than silent re-triage.

### Anti-Pattern 5: Separate Query for Each Sender's Emails During Re-Triage Sweep

**What people do:** For each sender being re-triaged, call `query_emails(sender=sender)` with no mailbox filter, which fetches EVERY email ever sent by that sender.
**Why it's wrong:** Queries with no mailbox filter and no date range scan the entire mailbox. For active senders, this returns hundreds of emails and overwhelms the move batch.
**Do this instead:** Scope the re-triage sweep to emails in the OLD destination mailbox (the one corresponding to the old group's category). This is a bounded query: `query_emails(old_dest_mailbox_id, sender=sender)`. It is precise and bounded. Screener sweep is a separate step for any emails still in Screener.

---

## Integration Points

### Config → Workflow

`MailroomSettings.label_to_category_mapping` is the primary interface. `ScreenerWorkflow` reads category attributes (`add_to_inbox`, `contact_group`, `destination_mailbox`) from `ResolvedCategory` objects. Any new field added to `ResolvedCategory` is automatically available to the workflow without interface changes.

### Config → Provisioner

`settings.required_mailboxes` and `settings.contact_groups` properties drive what `provisioner.py` creates. If `add_to_inbox=True` means "Inbox" must be in `required_mailboxes`, this property already handles it (Inbox is hardcoded there). No provisioner changes needed.

### Config → Sieve Guidance

`sieve_guidance.py` iterates categories to generate Fastmail filter rules. If category semantics change (children have own groups, not inherited groups), the sieve guidance output automatically updates because it reads from resolved categories. Verify sieve output is still correct after resolving with additive semantics.

### JMAPClient.call() → Batching

`call()` already accepts a list of method call triples and returns a list of responses in the same order. `batch_query_emails()` is built entirely on `call()` — no protocol changes needed. The JMAP spec supports arbitrary numbers of method calls in one request.

### CardDAVClient Groups Cache

`self._groups` is populated by `validate_groups()` at startup. `remove_from_group()` must work with this cache the same way `add_to_group()` does — use `self._groups[group_name]["href"]` to build the group URL, update `self._groups[group_name]["etag"]` after successful PUT. No cache invalidation issues since group membership change only modifies the group vCard's ETag, not the group's href or uid.

---

## Sources

- Mailroom codebase: `src/mailroom/` — all source files directly inspected (HIGH confidence)
- `src/mailroom/core/config.py` — TriageCategory, ResolvedCategory, resolve_categories(), _default_categories() (HIGH confidence)
- `src/mailroom/workflows/screener.py` — poll(), _collect_triaged(), _process_sender(), _check_already_grouped(), _get_destination_mailbox_ids() (HIGH confidence)
- `src/mailroom/clients/jmap.py` — call(), query_emails(), batch_move_emails() (HIGH confidence)
- `src/mailroom/clients/carddav.py` — add_to_group(), check_membership(), upsert_contact() (HIGH confidence)
- `src/mailroom/__main__.py` — main loop, HealthHandler, SSE thread lifecycle (HIGH confidence)
- `.planning/milestones/v1.1-research/ARCHITECTURE.md` — v1.1 architecture decisions and rationale (HIGH confidence)
- `.planning/PROJECT.md` — v1.2 target features, pre-v1.2 research note on JMAP label mailbox scanning (HIGH confidence)
- `.planning/todos/pending/2026-02-25-scan-for-action-labels-beyond-screener-mailbox.md` — problem statement for label scanning (HIGH confidence)
- `.planning/todos/pending/2026-02-26-sweep-workflow-re-label-archived-emails-by-contact-group-membership.md` — re-triage problem statement (HIGH confidence)
- [RFC 8620 Section 5.1: Method Calls](https://www.rfc-editor.org/rfc/rfc8620#section-5.1) — JMAP batched method calls in single request (HIGH confidence)

---

*Architecture research for: v1.2 Triage Pipeline v2*
*Researched: 2026-03-02*
