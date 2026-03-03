# Phase 12: Label Scanning - Research

**Researched:** 2026-03-03
**Domain:** JMAP batched queries, screener workflow refactoring
**Confidence:** HIGH

## Summary

Phase 12 replaces sequential per-label `Email/query` calls in `_collect_triaged()` with a single batched JMAP request. The existing `JMAPClient.call()` method already supports multiple method calls per request -- the infrastructure is in place. The change is entirely internal to `_collect_triaged()` and does not alter the method's return signature, `_process_sender` behavior, or poll orchestration.

The key technical challenge is parsing a batch response where individual `Email/query` calls may succeed or fail independently. JMAP RFC 8620 specifies that per-method errors appear as `["error", {...}, "call-id"]` tuples in `methodResponses` and do NOT cause the entire batch to fail -- subsequent methods continue processing. The implementation must detect these error tuples and handle them gracefully.

**Primary recommendation:** Refactor `_collect_triaged()` to build a list of `Email/query` method calls (one per triage label), send them all via a single `self._jmap.call()`, and parse the batched response with per-method error detection. The error filtering (`@MailroomError` check) can optionally be included in the same batch.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Scan ALL configured `@To*` triage label mailboxes on every poll -- no configurable subset
- Batched queries for ~10 labels complete in under 1s (validated by research script)
- System labels (`@MailroomError`, `@MailroomWarning`) included in the batch scan as today
- Batch only `Email/query` discovery calls into a single JMAP HTTP request
- Sender fetching (`Email/get` for sender addresses) stays as a separate follow-up call
- No JMAP result references -- keep it simple, avoid chaining complexity
- Graceful degradation: if one label query fails in the batch, log it and continue processing successful labels
- Failed labels are retried automatically on next poll (triage labels remain in place)
- Escalating log severity: first failure = WARNING, consecutive failures for the same label = ERROR
- Self-healing: counter resets when the label query succeeds again
- No provenance tracking needed in Phase 12
- Sweep continues to operate on Screener only (existing behavior)
- `add_to_inbox` fires only for swept (Screener-origin) emails -- correct by construction since sweep queries Screener
- Phase 12 will NOT be shipped independently -- it ships together with Phase 13

### Claude's Discretion
- Whether error-filtering (`@MailroomError` check) is included in the same batch or stays separate
- Exact escalation threshold for consecutive failures (e.g., 3 or 5 polls)
- Internal implementation of batch response parsing
- Test structure and organization

### Deferred Ideas (OUT OF SCOPE)
- JMAP result references for chaining Email/query -> Email/get in one request -- future optimization
- Provenance tracking (which mailbox each email was in) -- Phase 13 will handle as part of re-triage
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCAN-01 | Triage labels discovered by querying label mailbox IDs directly (not limited to Screener mailbox) | Batched `Email/query` with `inMailbox` filter per label, sent via existing `JMAPClient.call()` -- same filter pattern as current `query_emails()` |
| SCAN-02 | All label mailbox queries batched into single JMAP HTTP request | `JMAPClient.call()` already accepts `list[method_call]` and sends them in one HTTP POST -- no new infrastructure needed |
| SCAN-03 | Per-method errors in batched JMAP responses detected and handled (not silently dropped) | RFC 8620 defines error responses as `["error", {type, description}, call_id]` -- detection is a simple check on `response[0] == "error"` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | (existing) | HTTP client for JMAP calls | Already used in JMAPClient |
| structlog | (existing) | Structured logging | Already used throughout workflow |
| pydantic | (existing) | Config and settings | Already used for MailroomSettings |
| pytest | (existing) | Unit testing | Already used in test suite |

### Supporting
No new libraries needed. This phase is a pure refactor of existing code using existing dependencies.

## Architecture Patterns

### Current Code Structure (What Changes)

```
src/mailroom/
  workflows/
    screener.py        # _collect_triaged() -- PRIMARY CHANGE TARGET
  clients/
    jmap.py            # JMAPClient.call() -- ALREADY SUPPORTS BATCHING
  core/
    config.py          # triage_labels property -- USED AS-IS
```

### Pattern 1: Batched Email/query Construction

**What:** Build a list of `["Email/query", {...}, "q{i}"]` method calls, one per triage label, and send them all in one `self._jmap.call()` invocation.

**When to use:** Every `_collect_triaged()` call during poll.

**Example:**
```python
# Source: existing batched_vs_sequential.py research script (lines 74-88)
method_calls = []
for i, label_name in enumerate(self._settings.triage_labels):
    label_id = self._mailbox_ids[label_name]
    method_calls.append([
        "Email/query",
        {
            "accountId": self._jmap.account_id,
            "filter": {"inMailbox": label_id},
            "limit": 100,
        },
        f"q{i}",
    ])

responses = self._jmap.call(method_calls)
```

### Pattern 2: Per-Method Error Detection in Batch Response

**What:** JMAP RFC 8620 specifies that when a method call fails within a batch, the server returns `["error", {"type": "...", ...}, "call-id"]` at that position in `methodResponses`. Other method calls continue normally.

**When to use:** Parsing every batched response.

**Example:**
```python
# Source: RFC 8620 Section 3.6.1 (method-level errors)
for i, label_name in enumerate(self._settings.triage_labels):
    response = responses[i]
    method_name = response[0]

    if method_name == "error":
        # Per-method error -- log and skip this label
        error_type = response[1].get("type", "unknown")
        error_desc = response[1].get("description", "")
        log.warning("label_query_failed", label=label_name,
                     error_type=error_type, description=error_desc)
        continue

    # Success: response[1] contains {"ids": [...], "total": N}
    data = response[1]
    email_ids = data["ids"]
```

### Pattern 3: Escalating Failure Counter

**What:** Track consecutive failures per label. First failure = WARNING, after N consecutive failures = ERROR. Counter resets on success.

**When to use:** In `_collect_triaged()` or as workflow-level state.

**Recommendation for threshold:** Use 3 consecutive failures before escalating to ERROR. Rationale: polls run every 60s, so 3 failures = 3 minutes of degradation before escalating -- long enough to ride out brief transients, short enough to alert on persistent issues.

**Example:**
```python
# Instance variable on ScreenerWorkflow:
self._label_failure_counts: dict[str, int] = {}

# In batch response parsing:
if method_name == "error":
    count = self._label_failure_counts.get(label_name, 0) + 1
    self._label_failure_counts[label_name] = count
    if count >= 3:
        log.error("label_query_persistent_failure", label=label_name,
                   consecutive_failures=count)
    else:
        log.warning("label_query_failed", label=label_name,
                     consecutive_failures=count)
    continue

# On success -- reset the counter
self._label_failure_counts.pop(label_name, None)
```

### Pattern 4: Error Filtering in the Same Batch (Discretion Recommendation)

**What:** Include the `Email/get` call for `@MailroomError` filtering in the SAME batch as the `Email/query` calls, rather than as a separate round-trip.

**Recommendation:** Keep error filtering as a SEPARATE call. Reasons:
1. The error filtering `Email/get` call needs the email IDs from the `Email/query` results -- it depends on query results being parsed first.
2. Without JMAP result references (which are explicitly rejected), there is no way to chain query -> get in one batch.
3. The current approach (single `Email/get` after collecting all IDs) is already efficient -- one call regardless of how many labels.

**Conclusion:** Error filtering stays as a separate `self._jmap.call()` after batch query parsing. No change from current architecture.

### Anti-Patterns to Avoid
- **Pagination in batched queries:** The current `query_emails()` handles pagination with a while loop and multiple round-trips. The batched approach should use a generous `limit` (e.g., 100) per label. If any label has > 100 emails, we need a follow-up pagination pass for just that label. In practice, triage labels will rarely exceed a handful of emails.
- **Mixing call-ids across batches:** Use a predictable naming scheme like `q0`, `q1`, `q2` that maps 1:1 with the label index. Do NOT reuse call-ids.
- **Assuming response order matches call order:** RFC 8620 says "The output of the methods MUST be added to the methodResponses array in the same order that the methods are processed." Since methods are processed in order, this is safe -- but use call-ids for extra safety.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JMAP batching | Custom HTTP batching layer | `JMAPClient.call()` with multiple method_calls | Already implements the JMAP batch protocol correctly |
| Response correlation | Manual index tracking | Positional mapping (response[i] matches method_calls[i]) | JMAP spec guarantees same-order response; call-ids provide backup verification |
| Failure retry | Custom retry logic | Natural retry via poll loop -- triage labels stay in place | Existing TRIAGE-06 retry pattern handles this automatically |

**Key insight:** The batching mechanism already exists in `JMAPClient.call()`. Phase 12 is about using it from `_collect_triaged()` instead of calling `query_emails()` in a loop.

## Common Pitfalls

### Pitfall 1: Pagination Mismatch in Batched Queries
**What goes wrong:** Each `Email/query` in the batch returns up to `limit` results. If a label has more emails than the limit, the batch response only contains the first page.
**Why it happens:** Unlike `query_emails()` which loops for pagination, a single batched call returns one page per method.
**How to avoid:** Set `limit: 100` (same as current). After the batch, check if any label's `total > len(ids)`. For those labels, do a follow-up paginated query. In practice, triage label mailboxes almost never have > 100 emails.
**Warning signs:** `total` in the response is larger than the number of returned `ids`.

### Pitfall 2: Silent Error Dropping
**What goes wrong:** Code checks `response[1]["ids"]` without first checking if `response[0] == "error"`, causing a KeyError or silently processing empty data.
**Why it happens:** Developer assumes all methods in the batch succeed.
**How to avoid:** Always check `response[0]` before accessing `response[1]`. Error responses have `"error"` as the first element.
**Warning signs:** KeyError on `"ids"` or `"total"` during batch response parsing.

### Pitfall 3: Sender Fetch with Empty Email ID List
**What goes wrong:** If all label queries fail, `all_email_ids` is empty. Passing an empty list to `get_email_senders()` or `Email/get` wastes a round-trip.
**Why it happens:** No early return when batch produces zero results.
**How to avoid:** Check if `all_email_ids` is empty after batch parsing and return early (same pattern as current code at line 128-129 of screener.py).
**Warning signs:** Unnecessary JMAP calls with `ids: []`.

### Pitfall 4: Breaking the Return Signature
**What goes wrong:** `_collect_triaged()` signature changes, breaking `poll()` and all tests.
**Why it happens:** Refactoring scope creep -- adding provenance data to the return type.
**How to avoid:** Return type stays exactly `tuple[dict[str, list[tuple[str, str]]], dict[str, str | None]]`. Phase 13 may change this; Phase 12 must not.

### Pitfall 5: Failure Counter Persisting Across Restarts
**What goes wrong:** Counter stored in instance variable resets on restart, losing escalation history.
**Why it happens:** Instance variable lifecycle tied to process lifetime.
**How to avoid:** This is acceptable. The counter is meant for runtime monitoring, not persistence. On restart, counters reset to 0, which is correct behavior (fresh start).

## Code Examples

### Current _collect_triaged() (Sequential -- What Gets Replaced)
```python
# Source: src/mailroom/workflows/screener.py lines 94-101
for label_name in self._settings.triage_labels:
    label_id = self._mailbox_ids[label_name]
    email_ids = self._jmap.query_emails(label_id)  # One HTTP call per label
    if not email_ids:
        continue
    senders = self._jmap.get_email_senders(email_ids)  # Another HTTP call per label
    # ... process results
```

### New _collect_triaged() Pattern (Batched)
```python
# Build batched Email/query method calls
method_calls = []
for i, label_name in enumerate(self._settings.triage_labels):
    label_id = self._mailbox_ids[label_name]
    method_calls.append([
        "Email/query",
        {
            "accountId": self._jmap.account_id,
            "filter": {"inMailbox": label_id},
            "limit": 100,
        },
        f"q{i}",
    ])

# Single JMAP round-trip for all label queries (SCAN-02)
responses = self._jmap.call(method_calls)

# Parse responses with per-method error detection (SCAN-03)
label_email_ids: dict[str, list[str]] = {}
for i, label_name in enumerate(self._settings.triage_labels):
    response = responses[i]
    if response[0] == "error":
        # Handle per-method error with escalating severity
        self._handle_label_query_failure(label_name, response[1])
        continue
    # Reset failure counter on success
    self._label_failure_counts.pop(label_name, None)

    data = response[1]
    email_ids = data["ids"]
    if email_ids:
        label_email_ids[label_name] = email_ids

# Collect all email IDs across successful labels
all_email_ids = []
for ids in label_email_ids.values():
    all_email_ids.extend(ids)

if not all_email_ids:
    return {}, {}

# Single sender-fetch call for ALL emails across ALL labels
senders = self._jmap.get_email_senders(all_email_ids)

# Build the triaged dict (same structure as before)
raw: dict[str, list[tuple[str, str]]] = {}
sender_names: dict[str, str | None] = {}
for label_name, email_ids in label_email_ids.items():
    for email_id in email_ids:
        if email_id not in senders:
            self._log.warning("email_missing_sender",
                              email_id=email_id, label=label_name)
            continue
        sender_email, sender_name = senders[email_id]
        raw.setdefault(sender_email, []).append((email_id, label_name))
        if sender_email not in sender_names or (
            sender_names[sender_email] is None and sender_name is not None
        ):
            sender_names[sender_email] = sender_name

# Error filtering (separate call, same as current)
# ... existing @MailroomError filtering logic unchanged ...
```

### Test Pattern: Mocking Batched call()
```python
# In tests, jmap.call() must handle both batched Email/query and Email/get
def call_side_effect(method_calls):
    # Check if this is a batched Email/query call
    if len(method_calls) > 1 and method_calls[0][0] == "Email/query":
        # Return one response per query
        responses = []
        for mc in method_calls:
            label_id = mc[1]["filter"]["inMailbox"]
            # Return test data based on label_id
            if label_id == "mb-toimbox":
                responses.append(["Email/query", {"ids": ["email-1"], "total": 1}, mc[2]])
            else:
                responses.append(["Email/query", {"ids": [], "total": 0}, mc[2]])
        return responses
    # Email/get for error filtering (unchanged)
    if method_calls[0][0] == "Email/get":
        ids = method_calls[0][1].get("ids", [])
        return [["Email/get", {"list": [
            {"id": eid, "mailboxIds": {"mb-toimbox": True}} for eid in ids
        ]}, "g0"]]
    return []

jmap.call.side_effect = call_side_effect
```

### Test Pattern: Per-Method Error in Batch
```python
# Simulate one label query failing in the batch
def call_side_effect(method_calls):
    if len(method_calls) > 1 and method_calls[0][0] == "Email/query":
        responses = []
        for mc in method_calls:
            label_id = mc[1]["filter"]["inMailbox"]
            if label_id == "mb-toimbox":
                responses.append(["Email/query", {"ids": ["email-1"], "total": 1}, mc[2]])
            elif label_id == "mb-tofeed":
                # Simulate per-method error
                responses.append(["error", {
                    "type": "serverFail",
                    "description": "Temporary backend error"
                }, mc[2]])
            else:
                responses.append(["Email/query", {"ids": [], "total": 0}, mc[2]])
        return responses
    # ... rest unchanged
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sequential query_emails() per label | Batched Email/query in single call() | Phase 12 | ~10x fewer HTTP round-trips for discovery |
| No per-method error handling | Explicit error tuple detection in batch response | Phase 12 | SCAN-03 compliance; prevents silent data loss |

**Not deprecated/changed:**
- `query_emails()` method on JMAPClient -- still used for sender sweep queries (per-sender, with pagination)
- `get_email_senders()` -- still used as a separate follow-up call
- `_process_sender()` -- completely unchanged
- `_detect_conflicts()` -- completely unchanged
- `poll()` orchestration -- completely unchanged

## Open Questions

1. **Pagination in batch: should we handle it?**
   - What we know: Current `query_emails()` paginates with `while True` loop. Batched approach returns one page per method call.
   - What's unclear: Whether triage labels ever realistically have > 100 emails.
   - Recommendation: Implement with `limit: 100` and add a follow-up query for any label where `total > len(ids)`. Log a warning when pagination is needed (it should be rare).

2. **Sender fetching: one call or per-label calls?**
   - What we know: Currently, `get_email_senders()` is called once per label (sequential). After batching queries, we have all email IDs upfront.
   - What's unclear: Whether the sender fetch should be a single call for ALL email IDs across all labels.
   - Recommendation: Single `get_email_senders()` call with all email IDs. This is already more efficient than the current per-label approach and keeps the sender fetch as one round-trip.

3. **Test refactoring scope**
   - What we know: Existing tests mock `jmap.query_emails()` per-label. After batching, `_collect_triaged()` calls `jmap.call()` directly instead of `query_emails()`.
   - What's unclear: How much test infrastructure needs updating.
   - Recommendation: Tests will need to mock `jmap.call()` with a side_effect that handles both batched Email/query responses AND Email/get responses (for error filtering). The `jmap.query_emails` mock will no longer be called from `_collect_triaged()` but is still used in `_process_sender` for sweep.

## Sources

### Primary (HIGH confidence)
- [RFC 8620](https://www.rfc-editor.org/rfc/rfc8620.html) - Method-level error handling in JMAP batch responses, error types, response ordering guarantees
- `src/mailroom/clients/jmap.py` - `JMAPClient.call()` (line 60) already supports multiple method calls per request
- `src/mailroom/workflows/screener.py` - `_collect_triaged()` (line 82) is the refactor target
- `src/mailroom/core/config.py` - `triage_labels` property (line 382) provides all label names
- `.research/triage-label-scan/batched_vs_sequential.py` - Pre-v1.2 research script validates batched approach against live Fastmail

### Secondary (MEDIUM confidence)
- `.planning/phases/12-label-scanning/12-CONTEXT.md` - User decisions and design constraints

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies, all existing infrastructure
- Architecture: HIGH - `JMAPClient.call()` verified to support batching, research script proves it works against Fastmail
- Pitfalls: HIGH - RFC 8620 error format verified, codebase patterns well understood
- Error handling: HIGH - RFC 8620 explicitly documents per-method error responses

**Research date:** 2026-03-03
**Valid until:** Stable -- JMAP RFC 8620 is a published standard, unlikely to change
