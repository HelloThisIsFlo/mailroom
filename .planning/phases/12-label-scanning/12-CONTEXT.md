# Phase 12: Label Scanning - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace sequential per-label `Email/query` calls in `_collect_triaged()` with a single batched JMAP request that queries all triage label mailboxes at once. This is an infrastructure improvement — user-visible triage behavior stays identical. Sweep, filing, and `add_to_inbox` logic are unchanged. Re-triage behavior is Phase 13.

</domain>

<decisions>
## Implementation Decisions

### Scan scope
- Scan ALL configured `@To*` triage label mailboxes on every poll — no configurable subset
- Batched queries for ~10 labels complete in under 1s (validated by research script)
- System labels (`@MailroomError`, `@MailroomWarning`) included in the batch scan as today

### Batching strategy
- Batch only `Email/query` discovery calls into a single JMAP HTTP request
- Sender fetching (`Email/get` for sender addresses) stays as a separate follow-up call
- No JMAP result references — keep it simple, avoid chaining complexity

### Batch error handling
- Graceful degradation: if one label query fails in the batch, log it and continue processing successful labels
- Failed labels are retried automatically on next poll (triage labels remain in place)
- Escalating log severity: first failure = WARNING, consecutive failures for the same label = ERROR
- Self-healing: counter resets when the label query succeeds again
- Escalation threshold: Claude's discretion

### Screener provenance
- No provenance tracking needed in Phase 12
- Sweep continues to operate on Screener only (existing behavior)
- `add_to_inbox` fires only for swept (Screener-origin) emails — correct by construction since sweep queries Screener
- Phase 13 (re-triage) will handle emails discovered outside Screener with its own logic
- Phase 12 will NOT be shipped independently — it ships together with Phase 13

### Claude's Discretion
- Whether error-filtering (`@MailroomError` check) is included in the same batch or stays separate
- Exact escalation threshold for consecutive failures (e.g., 3 or 5 polls)
- Internal implementation of batch response parsing
- Test structure and organization

</decisions>

<specifics>
## Specific Ideas

- "Don't try to have a workaround so that phase 12 is complete that it could be shipped" — Phase 12 is a stepping stone to Phase 13, not a standalone release
- JMAP result references (backreferences like `#q0/ids`) are explicitly rejected as too complex — keep sender fetching as a separate call

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `JMAPClient.call()` (jmap.py:60): Already supports multiple method calls in a single request — this IS the batching mechanism
- `.research/triage-label-scan/batched_vs_sequential.py`: Pre-v1.2 research script validates batched approach against live Fastmail
- `_collect_triaged()` (screener.py:82): The method to refactor — replace sequential `query_emails()` loop with single batched `call()`
- `self._settings.triage_labels` (config.py): Already enumerates all `@To*` label names

### Established Patterns
- `query_emails()` uses `Email/query` with `inMailbox` filter — same filter goes into batch
- Error filtering uses `Email/get` with `mailboxIds` check — can potentially be batched alongside
- Batch chunking at BATCH_SIZE=100 for `Email/set` — similar pattern for response parsing

### Integration Points
- `_collect_triaged()` return signature stays identical: `tuple[dict[str, list[tuple[str, str]]], dict[str, str | None]]`
- `_process_sender()` is NOT modified — receives same data, behaves identically
- `poll()` orchestration flow unchanged — only the internal implementation of discovery changes
- EventSource push triggers poll() which calls _collect_triaged() — no SSE changes needed

</code_context>

<deferred>
## Deferred Ideas

- JMAP result references for chaining Email/query → Email/get in one request — future optimization, explicitly too complex for now
- Provenance tracking (which mailbox each email was in) — Phase 13 will handle as part of re-triage

</deferred>

---

*Phase: 12-label-scanning*
*Context gathered: 2026-03-03*
