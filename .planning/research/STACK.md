# Stack Research

**Domain:** Email triage pipeline evolution (v1.2 additions)
**Researched:** 2026-03-02
**Confidence:** HIGH

## Scope

This document covers ONLY what changes or is newly needed for v1.2 features:
- `add_to_inbox` flag separation from `destination_mailbox`
- Additive parent label propagation (child = own category + parent's labels)
- Label-based scanning via JMAP batched queries (multi-label → one round-trip)
- Re-triage: move sender between contact groups, re-file emails

The existing v1.1 stack is validated and deployed. All stack decisions from v1.1 carry forward unchanged.

---

## Existing Stack (DO NOT change)

From `pyproject.toml` (actual, post-v1.1):

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12 | Runtime |
| httpx | 0.28.1 | HTTP client (JMAP + CardDAV + SSE streaming) |
| vobject | 0.9.9 | vCard parsing/serialization |
| nameparser | 1.1.3 | Human name parsing for person contacts |
| pydantic-settings[yaml] | 2.13.1 | Config from YAML + env vars |
| pydantic | 2.12.5 | Data validation |
| structlog | 25.5.0 | Structured JSON logging |
| click | 8.3.1 | CLI framework |
| pytest | 9.0.2 | Testing |
| pytest-httpx | 0.36.0 | Mock httpx in tests |
| ruff | 0.15.2 | Linting + formatting |
| python-dotenv | 1.2.1 | Local .env file loading (dev only) |

**Note:** `requests>=2.32.5` appears in `pyproject.toml` but is NOT imported anywhere in `src/`. This is an orphan dependency — remove it as part of v1.2 tech debt cleanup.

---

## New Dependencies for v1.2

**None.**

All four v1.2 features are implementable using existing libraries. The table below explains why each feature requires no new dependency.

| Feature | Why No New Dependency Needed |
|---------|------------------------------|
| `add_to_inbox` flag separation | `TriageCategory` and `ResolvedCategory` are pydantic models. Adding `add_to_inbox: bool = False` is one field. No new library. |
| Additive parent label propagation | `resolve_categories()` is pure Python logic. Adding a `labels: list[str]` field to `ResolvedCategory` and updating the second-pass resolution loop requires no library. |
| JMAP batched queries | `JMAPClient.call()` already accepts a list of method calls. Send N `Email/query` calls in one `call([...N items...])` invocation. The HTTP layer (httpx) handles the single POST. No new library. |
| Re-triage (group reassignment) | `CardDAVClient.add_to_group()` uses GET-then-PUT with If-Match. A new `remove_from_group()` follows the inverse pattern using the same httpx client and vobject. No new library. |

---

## Feature-Specific Stack Details

### 1. `add_to_inbox` Flag Separation

**What changes:** `config.py` only. The current behavior conflates two concerns: "which mailbox does this triage category file into?" (`destination_mailbox`) and "should swept emails also appear in Inbox?" (`add_to_inbox`). Currently `destination_mailbox="Inbox"` for Imbox — the sweeper adds Inbox because destination IS Inbox. The fix separates these axes.

**Model changes:**

```python
# TriageCategory (user-facing input)
class TriageCategory(BaseModel):
    name: str
    label: str | None = None
    contact_group: str | None = None
    destination_mailbox: str | None = None
    add_to_inbox: bool | None = None   # NEW: None = inherit or derive
    contact_type: Literal["company", "person"] = "company"
    parent: str | None = None

# ResolvedCategory (computed)
@dataclass(frozen=True)
class ResolvedCategory:
    name: str
    label: str
    contact_group: str
    destination_mailbox: str
    add_to_inbox: bool           # NEW: concrete after resolution
    contact_type: str
    parent: str | None
```

**Derivation rule:** If `add_to_inbox` is None, derive as `destination_mailbox == "Inbox"`. This preserves v1.0 defaults without requiring config changes.

**Workflow change:** `_get_destination_mailbox_ids` in `screener.py` uses `category.add_to_inbox` instead of checking `destination_mailbox == "Inbox"`. The Inbox ID is always resolved at startup (already present in `mailbox_ids`).

**Stack involvement:** `config.py`, `screener.py`. No new imports.

---

### 2. Additive Parent Label Propagation

**What changes:** `config.py` resolution logic + `ResolvedCategory` shape. Current parent inheritance overwrites child's `contact_group` and `destination_mailbox`. New behavior: child is an independent category that ALSO carries parent's labels (for sweeping). This enables a child category (e.g. `Person`) to sweep emails out of the same label mailboxes as the parent (e.g. `Imbox`) when re-filing.

**Model changes:**

The `ResolvedCategory.labels` field becomes a list of labels to scan for, not a single label:

```python
@dataclass(frozen=True)
class ResolvedCategory:
    name: str
    label: str           # own triage label (the one user applies)
    labels: list[str]    # NEW: own label + parent's labels (for scanning)
    contact_group: str
    destination_mailbox: str
    add_to_inbox: bool
    contact_type: str
    parent: str | None
```

**Resolution logic:** After first pass (own-field derivation), second pass builds `labels` by collecting own label + walking up the parent chain. A child that had `parent="Imbox"` gets `labels=["@ToPerson", "@ToImbox"]`. This is a list concatenation of resolved labels in order.

**Workflow change:** `_collect_triaged` currently iterates `self._settings.triage_labels` (one label per category). With additive labels, scanning must query each unique label mailbox. Since a label can appear in multiple categories' `labels` lists, deduplicate before querying. The JMAP batch call sends one `Email/query` per unique label mailbox ID.

**Stack involvement:** `config.py` resolution logic. Downstream impacts in `screener.py` (`_collect_triaged`, `required_mailboxes`). No new imports.

---

### 3. JMAP Batched Queries for Label-Based Scanning

**What changes:** `JMAPClient` (new method) + `ScreenerWorkflow._collect_triaged` call pattern.

**Current approach (N round-trips):**

```python
# _collect_triaged makes N sequential HTTP requests:
for label_name in self._settings.triage_labels:
    label_id = self._mailbox_ids[label_name]
    email_ids = self._jmap.query_emails(label_id)   # 1 HTTP call each
```

**New approach (1 round-trip):**

JMAP's `methodCalls` array accepts any number of calls in a single HTTP POST. The existing `JMAPClient.call()` already takes a list — this is just a usage pattern change.

```python
# New JMAPClient method:
def query_emails_batch(self, mailbox_ids: list[str]) -> dict[str, list[str]]:
    """Query email IDs for N label mailboxes in a single JMAP request.

    Returns: dict mapping mailbox_id -> list of email IDs.
    """
    if not mailbox_ids:
        return {}

    method_calls = [
        [
            "Email/query",
            {
                "accountId": self.account_id,
                "filter": {"inMailbox": mailbox_id},
                "limit": BATCH_SIZE,
                "position": 0,
            },
            f"q{i}",
        ]
        for i, mailbox_id in enumerate(mailbox_ids)
    ]

    responses = self.call(method_calls)

    result: dict[str, list[str]] = {}
    for i, mailbox_id in enumerate(mailbox_ids):
        data = responses[i][1]
        result[mailbox_id] = data["ids"]
        # TODO: handle pagination if total > BATCH_SIZE
    return result
```

**Pagination note:** `query_emails()` handles pagination. `query_emails_batch()` should either also paginate (subsequent individual calls for overflowing mailboxes) or assert `total <= limit` in the initial response and fetch the remainder. In practice, triage label mailboxes contain at most a handful of emails — pagination is unlikely but must be handled correctly. The safe implementation: check `total > len(ids)` per response and follow up with sequential calls for overflowing mailboxes only.

**Why this matters:** With 5 triage labels, this reduces 5 HTTP round-trips to 1 for the scan phase. With user-configured labels (potentially more), the savings scale.

**RFC verification:** JMAP RFC 8620 Section 3.1 confirms method calls in `methodCalls` array are processed in order, server may interleave concurrent requests but not calls within one request. Each `Email/query` call is independent (no backreferences needed here). `inMailbox` filter accepts exactly one mailbox ID (RFC 8621 Section 4.4.1 — `inMailboxOtherThan` is for exclusion; multi-mailbox union queries require multiple calls). Confidence: HIGH (from JMAP spec and existing implementation knowledge).

**Stack involvement:** `JMAPClient` (new `query_emails_batch` method). `ScreenerWorkflow._collect_triaged` (call pattern). No new imports.

---

### 4. Re-Triage: CardDAV Group Reassignment

**What changes:** New `remove_from_group` method on `CardDAVClient`. New `move_to_group` orchestration (remove from old group, add to new group). New workflow logic in `ScreenerWorkflow._process_sender` for re-triage path.

**Detection:** Re-triage is triggered when `_check_already_grouped` finds the sender in a DIFFERENT group than the target. Currently this is treated as a conflict (applies `@MailroomError` and stops). In v1.2, when the user has applied a new triage label, this is intentional reassignment.

**Disambiguation:** Conflict (user applied two different labels to emails from same sender in one poll cycle) vs. re-triage (user previously triaged sender, now applies a different label to move them). The signals differ:
- **Conflict**: sender has emails with label A AND label B simultaneously in the SAME poll cycle
- **Re-triage**: sender has emails with label B only, but contact is already in group A

The existing `_check_already_grouped` already handles detection for re-triage (returns existing group name). The change is what we DO with that information.

**New CardDAV method:**

```python
def remove_from_group(
    self,
    group_name: str,
    contact_uid: str,
    max_retries: int = 3,
) -> str:
    """Remove a contact from a group by modifying the group's vCard.

    Fetches the group vCard, removes the X-ADDRESSBOOKSERVER-MEMBER
    entry for this contact, and PUTs it back with If-Match.
    Retries on 412 Precondition Failed (ETag conflict).

    Returns: new ETag after successful PUT.
    Raises: RuntimeError after exhausting retries.
    """
    # Pattern: inverse of add_to_group()
    # GET group vCard, filter out member_urn, PUT back
```

**Orchestration in CardDAVClient:**

```python
def move_to_group(
    self,
    contact_uid: str,
    from_group: str,
    to_group: str,
) -> None:
    """Atomic group reassignment: remove from old, add to new."""
    self.remove_from_group(from_group, contact_uid)
    self.add_to_group(to_group, contact_uid)
```

**Retry safety for re-triage:** If `remove_from_group` succeeds but `add_to_group` fails, the contact is in no group. On next poll, `_check_already_grouped` returns `None` (not in any group), so the re-triage path proceeds to `add_to_group` again — which is safe and self-healing.

**Warning label for re-triage:** Per PROJECT.md, re-triage applies `@MailroomWarning` to notify the user of the group change. `LabelSettings.mailroom_warning` already exists. The existing `_apply_warning_label` method is reusable.

**Stack involvement:** `CardDAVClient` (new `remove_from_group`, `move_to_group`). `ScreenerWorkflow._process_sender` (re-triage branch). No new imports — same httpx + vobject pattern as `add_to_group`.

---

## Dependency Changes

### Remove `requests` (tech debt cleanup)

`requests>=2.32.5` is in `pyproject.toml` but unused. The project uses httpx for all HTTP. Remove it.

```toml
# Before:
dependencies = [
    "click>=8.1",
    "httpx",
    "nameparser>=1.1.3",
    "pydantic-settings[yaml]",
    "requests>=2.32.5",   # remove this
    "structlog",
    "vobject>=0.9.9",
]

# After:
dependencies = [
    "click>=8.1",
    "httpx",
    "nameparser>=1.1.3",
    "pydantic-settings[yaml]",
    "structlog",
    "vobject>=0.9.9",
]
```

**Command:** `uv remove requests`

---

## What NOT to Add

| Avoid | Why | Notes |
|-------|-----|-------|
| `httpx-sse` | v1.1 research recommended it, but the implementation chose `httpx.stream()` + raw `iter_lines()` (already in `eventsource.py`). The custom implementation works and is tested. Don't add a dependency to replace working code. | If SSE parsing breaks, the fix is inside `eventsource.py` — not a library swap. |
| `tenacity` | Re-triage retry is ETag-conflict retry (already done in `add_to_group`). The same pattern applies to `remove_from_group`: loop with max_retries, retry on 412. 8 lines of code, no library needed. | |
| JMAP library (`jmapc`, etc.) | v1.0 research ruled this out. All JMAP operations use `JMAPClient.call()` on raw httpx. The batched query is a list construction change, not a protocol complexity increase. | |
| `lxml` | XML parsing for CardDAV stays with stdlib `xml.etree.ElementTree`. No XPath complexity requiring lxml in v1.2. | |
| New test framework | `pytest` + `pytest-httpx` handles all v1.2 testing. Mocking batched JMAP responses: return a list of N response tuples. Mocking CardDAV group operations: same pattern as existing `add_to_group` tests. | |

---

## Integration Points

### `config.py` Changes

All four features touch `config.py`. The changes are additive to `TriageCategory` and `ResolvedCategory` and the `resolve_categories()` function:

1. `TriageCategory`: add `add_to_inbox: bool | None = None`
2. `ResolvedCategory`: add `add_to_inbox: bool`, add `labels: list[str]`
3. `resolve_categories()`: update second pass for both new fields
4. `MailroomSettings.required_mailboxes`: no change (label mailboxes already included via `c.label`)

### `jmap.py` Changes

One new method (`query_emails_batch`). Existing methods unchanged. The screener workflow's call site changes, not the existing `query_emails` (which remains for single-mailbox queries used elsewhere).

### `carddav.py` Changes

Two new methods (`remove_from_group`, `move_to_group`). Existing `add_to_group` and `check_membership` unchanged.

### `screener.py` Changes

`_collect_triaged`: replace per-label loop with `query_emails_batch` call. Handle de-duplication of label IDs (additive parent labels mean one label ID may appear in multiple categories).

`_process_sender`: add re-triage branch before the existing "already-grouped" error path.

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| No new dependencies | HIGH | All four features are logic changes in existing models and client methods. Verified by reading actual source code. |
| JMAP batch query (N calls in 1 request) | HIGH | `JMAPClient.call()` already takes a list. RFC 8620 Section 3.1 confirms methodCalls array batching. Existing code already does 2-call batches in `__main__.py` pattern. |
| `inMailbox` is single-mailbox | HIGH | RFC 8621 confirmed: `inMailbox` is a single ID. `inMailboxOtherThan` is for exclusion. Multi-mailbox union requires N separate `Email/query` calls — which the batch approach handles. |
| CardDAV group removal | HIGH | `remove_from_group` is the inverse of `add_to_group` (GET-filter-PUT with If-Match). Same ETag retry pattern. Already proven by `add_to_group` in production. |
| `requests` is unused orphan | HIGH | `grep -r "import requests" src/` returns nothing. Safe to remove. |
| Config model changes backward compatible | HIGH | Existing defaults preserved. `add_to_inbox=None` derives to same behavior as v1.1. |

---

## Sources

- Existing codebase: `src/mailroom/clients/jmap.py`, `src/mailroom/clients/carddav.py`, `src/mailroom/core/config.py`, `src/mailroom/workflows/screener.py` — source of truth for current implementation (HIGH confidence)
- `pyproject.toml` — actual dependency list (HIGH confidence, read directly)
- [RFC 8620 Section 3: JMAP Method Calls and Request Batching](https://www.rfc-editor.org/rfc/rfc8620#section-3) — methodCalls array batching confirmed (HIGH confidence)
- [RFC 8621 Section 4.4.1: Email/query filter conditions](https://www.rfc-editor.org/rfc/rfc8621#section-4.4.1) — `inMailbox` (single ID), `inMailboxOtherThan` (exclusion list) (HIGH confidence via web search confirmation)
- [jmap.io client guide](https://jmap.io/client.html) — backreferences and batch patterns (HIGH confidence)
- `.planning/PROJECT.md` — v1.2 feature goals and pre-research notes (HIGH confidence)
- `.planning/milestones/v1.1-research/STACK.md` — v1.1 stack decisions and rationale (HIGH confidence)

---

*Stack research for: Mailroom v1.2 Triage Pipeline v2*
*Researched: 2026-03-02*
