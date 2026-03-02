# Project Research Summary

**Project:** Mailroom v1.2 — Triage Pipeline v2
**Domain:** Email triage automation (Fastmail JMAP + CardDAV) — evolutionary pipeline enhancement
**Researched:** 2026-03-02
**Confidence:** HIGH

## Executive Summary

Mailroom v1.2 is an incremental but substantive evolution of a working, deployed v1.1 pipeline. The four core features — inbox flag separation, additive parent label propagation, label-based scanning, and re-triage — are all achievable with zero new dependencies. Every required capability (pydantic config models, httpx HTTP, vobject CardDAV, JMAP method batching) already exists in the stack. The changes are targeted: primarily `core/config.py`, `workflows/screener.py`, `clients/jmap.py`, and `clients/carddav.py`, with the outer loop (`__main__.py`, `eventsource.py`, Helm) untouched.

The recommended build strategy is strict sequencing by data flow layer: config model changes first (all other layers read from them), then client method additions (workflow assumes they exist), then workflow wiring (uses both config and clients), then re-triage as a separate final phase because it carries the most behavioral risk. Tech debt cleanup from v1.1 is a light pre-flight that unblocks the config layer changes cleanly. This ordering also isolates test failure blast radius: config tests fail only when config is wrong, client tests only when clients are wrong, workflow tests only when wiring is wrong.

The most significant risk is the re-triage operation: CardDAV group reassignment is two non-atomic mutations. A partial failure leaves a contact in both groups (if add-succeeds-remove-fails) or neither (if remove-first fails). The mitigation is explicit mutation ordering (add-to-new-group FIRST, then remove-from-old-group) and designing around the retry safety invariant: the triage label is always removed last, so any partial failure leaves the label in place and auto-retries on the next poll. The remaining pitfalls are configuration migration risks (new fields on frozen dataclasses must have defaults) and a subtle silent-failure mode in the JMAP batch scanner (per-method error handling must be explicit, not assumed).

## Key Findings

### Recommended Stack

The v1.1 stack carries forward unchanged. No new dependencies are needed for any v1.2 feature. All protocol requirements (JMAP method call batching, CardDAV group mutation, pydantic config extension) are already handled by existing libraries. One dependency removal is warranted: `requests>=2.32.5` is an orphan entry in `pyproject.toml` with no imports in `src/` — remove via `uv remove requests`.

**Core technologies (unchanged from v1.1):**
- **Python 3.12 + httpx 0.28.1:** All JMAP and CardDAV HTTP; `call()` already accepts a list of method call triples for batch requests
- **pydantic-settings 2.13.1 + pydantic 2.12.5:** Config models; new fields must have defaults to preserve backward compat with existing `config.yaml` (frozen dataclass default pattern)
- **vobject 0.9.9:** CardDAV vCard parsing; `remove_from_group()` follows the same GET-filter-PUT pattern as `add_to_group()`
- **structlog 25.5.0 + pytest 9.0.2 + pytest-httpx 0.36.0:** Logging and test infrastructure; no changes

For full dependency details see `.planning/research/STACK.md`.

### Expected Features

All five features are P1 — they define the milestone. No table-stakes feature is optional.

**Must have (defines v1.2):**
- **Tech debt cleanup (Feature 5)** — 4 items from v1.1 audit; clears the path for config changes (notably: `resolved_categories` public property needed by Feature 2's parent chain walking)
- **`add_to_inbox` flag separation (Feature 1)** — decouples inbox visibility from filing destination; makes `Imbox` config semantically correct; unblocks child category independence
- **Additive parent label propagation (Feature 2)** — children become fully independent categories that also carry parent labels; removes the current field-overwrite inheritance that makes children indistinguishable from parents
- **Label-based scanning (Feature 3)** — fixes a silent partial-success bug: sweep currently only searches Screener; scanning by label mailbox ID finds emails wherever they live, which is correct per the JMAP model
- **Re-triage / group reassignment (Feature 4)** — converts the current `@MailroomError` dead-end for "sender in wrong group" into an intentional, audited group move with `@MailroomWarning`

**Should have (add after v1.2 validation):**
- Batched JMAP label queries (optimization: 5 round-trips → 1 for `_collect_triaged()`)
- Human integration test for re-triage (`human-tests/test_N_retriage.py`)
- `add_to_inbox` inheritance through parent chain (if not included in Feature 2 phase)

**Defer (v1.3+):**
- Sweep workflow (self-healing label integrity from archive-swipe label removal)
- JMAP Contacts migration (replace CardDAV with RFC 9610)
- Programmatic sieve rule creation

For full feature analysis and dependency graph see `.planning/research/FEATURES.md`.

### Architecture Approach

The architecture is a targeted extension of the existing layered design: config → clients → workflow. No component outside `core/config.py`, `workflows/screener.py`, `clients/jmap.py`, and `clients/carddav.py` changes. The outer loop, EventSource infrastructure, health endpoint, provisioner, and Helm chart are all unchanged. Human tests 1–16 continue to pass unchanged for non-parent-child, non-reassignment paths.

**Major components and what changes:**
1. **`core/config.py`** — `TriageCategory` gets `add_to_inbox: bool = False`; `ResolvedCategory` gets `add_to_inbox: bool`; `resolve_categories()` second pass drops field-overwrite inheritance, replaces with `add_to_inbox` propagation from parent chain; `_validate_categories()` updated in same commit as resolver to stay in sync
2. **`clients/jmap.py`** — new `batch_query_emails(mailbox_ids)` method (N label queries in 1 HTTP request); `query_emails()` gains optional `mailbox_id` for sender-only queries needed by re-triage
3. **`clients/carddav.py`** — new `remove_from_group(group_name, contact_uid)` method (ETag-retry pattern identical to `add_to_group()`); this enables the CardDAV half of re-triage
4. **`workflows/screener.py`** — `_collect_triaged()` uses batched queries; `_get_destination_mailbox_ids()` includes Inbox when `add_to_inbox=True`; `_process_sender()` gains re-triage branch; new `_retriage_sender()` method for the full reassignment sequence

For full architecture details and data flow diagrams see `.planning/research/ARCHITECTURE.md`.

### Critical Pitfalls

1. **CardDAV group reassignment is two non-atomic mutations** — add-to-new-group first, THEN remove-from-old-group; this is the safe partial-failure order. A failure after add (but before remove) leaves the contact in both groups, which surfaces as `@MailroomError` on next poll — recoverable. Never remove-first.

2. **`add_to_inbox` field with no default breaks all existing `config.yaml` files** — define as `add_to_inbox: bool = False` (not `Optional[bool]`). Pydantic v2 requires `Optional[T]` fields without defaults to be explicitly provided. Omitting the default causes pod CrashLoopBackOff after upgrade. Add a regression test that loads a v1.1-era config fixture with no `add_to_inbox` key and asserts successful parse.

3. **Batch scan silently drops per-method errors** — JMAP method-level errors do not propagate to the request level. `responses[i][0]` can be `"error"` while other responses succeed. Without explicit per-method error checking, a failed label mailbox query is silently skipped. Add a `check_method_response()` helper; apply it before accessing `responses[i][1]` in every batch loop. Unit test with a mock response containing one `"error"` result.

4. **Validation/resolver consistency on the additive model** — `_validate_categories()` was written against the old field-overwrite inheritance semantics. Update it in the same commit as `resolve_categories()`. If they drift, validation passes configs that resolve incorrectly (notably the default Person/Imbox pair).

5. **Re-triage sweep must query ALL destination mailboxes, not just Screener** — the existing `_process_sender()` sweeps `screener_id` only. For re-triage, the sender's emails may already be in Paper Trail, Feed, etc. Scoping the sweep to Screener silently succeeds (group moves, label removed) but leaves existing emails in the old destination. Re-triage sweep must query `old_dest_mailbox_id` for the sender, not `screener_id`.

For full pitfall details, recovery strategies, and the "looks done but isn't" checklist see `.planning/research/PITFALLS.md`.

## Implications for Roadmap

Based on combined research, the features group naturally into 5 phases ordered by data flow dependency. Each phase has a clear scope boundary and can be tested in isolation before the next phase builds on it.

### Phase 1: Tech Debt Cleanup
**Rationale:** All four v1.1 carry-forward items are independent of the feature work. The `resolved_categories` public property (item 3) is directly needed by Feature 2's parent chain walking. Clearing these first gives a clean baseline for the config changes, eliminates stale test artifacts before new tests are added, and closes the v1.1 audit.
**Delivers:** 4 audit items closed; `resolved_categories` public property on `MailroomSettings`; `sieve_guidance.py` uses public interface; `conftest.py` cleaned; `test_13` polling interval fixed; Phase 09.1.1 `VERIFICATION.md` written
**Avoids:** Carrying stale test fixtures and private interface access into the config refactor phases

### Phase 2: Config Layer — Inbox Flag + Additive Parent Labels
**Rationale:** Config changes are the foundation — every downstream layer (workflow, clients) reads from `ResolvedCategory`. Features 1 and 2 both modify `TriageCategory`, `ResolvedCategory`, and `resolve_categories()`. Doing them together in one phase avoids touching the same resolution logic twice and ensures `_validate_categories()` is updated atomically with the resolver. The existing test suite is the backward-compat gate: it must pass with no changes to fixture YAML files.
**Delivers:** `add_to_inbox: bool = False` field on both model layers; `add_to_inbox` propagation through parent chain; removal of field-overwrite inheritance (`contact_group` and `destination_mailbox` no longer copy from parent); children resolve to fully independent categories; updated default categories (Imbox gets `add_to_inbox=True`; Person gets own group/mailbox); `_validate_categories()` updated in same commit
**Features:** Feature 1 + Feature 2
**Avoids:** Pitfall 2 (field without default), Pitfall 3 (resolver/validator drift), Pitfall 6 (`ResolvedCategory` construction sites)

### Phase 3: JMAP Client — Batch Query + Optional Mailbox Filter
**Rationale:** New client capabilities must exist before the workflow can use them. This phase is isolated to `jmap.py` with no workflow changes, making it independently testable. JMAP method batching is a low-risk, well-understood pattern on existing infrastructure.
**Delivers:** `batch_query_emails(mailbox_ids)` method returning one HTTP request for N label mailboxes; `query_emails(mailbox_id=None)` optional mailbox filter for sender-only queries used by re-triage; per-method error handling in batch response parsing
**Features:** Infrastructure for Feature 3 + Feature 4
**Avoids:** Pitfall 4 (batch scan swallows per-method errors)

### Phase 4: CardDAV Client — Group Removal
**Rationale:** Parallel to Phase 3 — also a pure client addition with no workflow dependency. `remove_from_group()` is the inverse of the already-proven `add_to_group()`: GET-filter-PUT with ETag retry. Can be developed alongside Phase 3 or immediately after.
**Delivers:** `remove_from_group(group_name, contact_uid)` with ETag-safe retry; `move_to_group(contact_uid, from_group, to_group)` orchestration wrapper
**Features:** Infrastructure for Feature 4
**Avoids:** Pitfall 1 (mutation order is add-then-remove, encoded in `move_to_group`)

### Phase 5: Workflow Wiring — Label Scanning + Inbox Flag Behavior
**Rationale:** Wire Phase 2 config + Phase 3 client into the workflow. `_collect_triaged()` switches from sequential per-label queries to `batch_query_emails()`. `_get_destination_mailbox_ids()` uses the `add_to_inbox` flag. This phase does NOT include re-triage — the wrong-group path still errors, keeping the blast radius small. All human tests 1–16 must pass at the end of this phase.
**Delivers:** `_collect_triaged()` uses batched JMAP queries; label scanning covers all labeled emails (not Screener-scoped); `_get_destination_mailbox_ids()` includes Inbox ID when `add_to_inbox=True`; existing pipeline fully functional with new config semantics
**Features:** Feature 3 (core fix), Feature 1 (wired into pipeline)
**Avoids:** Pitfall 7 (multi-label email deduplication strategy), Pitfall 10 (implicit `destination_mailbox == "Inbox"` check removed)

### Phase 6: Re-Triage
**Rationale:** Highest behavioral risk — new `_retriage_sender()` method, CardDAV group move, sweep from all destination mailboxes, `@MailroomWarning` application. Isolated as a final phase so all supporting infrastructure (label-based sweep scope, `remove_from_group()`, optional mailbox filter on `query_emails()`) is proven before the most complex orchestration is built. A focused human test for re-triage is the validation gate.
**Delivers:** `_process_sender()` re-triage branch instead of error on wrong-group; `_retriage_sender()` method (remove from old group → add to new group → sweep old destination → apply warning → remove triage label); structured `group_reassigned` log event; `@MailroomWarning` on triggering email(s); semantic fix (old `already_grouped` warning → now an informational re-triage path)
**Features:** Feature 4
**Avoids:** Pitfall 1 (add-then-remove order enforced), Pitfall 5 (sweep from old destination mailbox, not Screener), Pitfall 9 (group membership check caching per poll cycle)

### Phase Ordering Rationale

- **Config before clients and workflow:** `ResolvedCategory` is the data contract. Once its shape is settled, client and workflow changes can proceed in parallel with a clear contract.
- **Clients before workflow:** The workflow assumes `batch_query_emails()` and `remove_from_group()` exist. Stubbing them in tests is possible but building the real methods first makes the workflow integration straightforward.
- **Label scanning before re-triage:** Re-triage's old-label sweep relies on label-based queries (finding sender emails in old destination mailbox). Phase 5 proves this query pattern before Phase 6 uses it for the more complex re-triage sweep.
- **Re-triage last:** Highest risk, most novel behavior, most integration surface. Deserves its own phase with focused review and a dedicated human test.
- **Tech debt before features:** The `resolved_categories` property is needed by Feature 2. Doing tech debt first also gives a clean test baseline before the config model changes multiply the surface area.

### Research Flags

Phases with well-documented patterns (skip `/gsd:research-phase`):
- **Phase 1 (Tech Debt):** 4 targeted fixes with no design uncertainty; patterns are explicit in the v1.1 audit
- **Phase 3 (JMAP Client):** JMAP batching is RFC-documented and already used in the codebase; pattern is clear
- **Phase 4 (CardDAV Client):** `remove_from_group()` is the inverse of `add_to_group()` — same ETag-retry pattern, same vobject mutation

Phases that merit pre-phase review (not full research, but explicit design validation):
- **Phase 2 (Config Layer):** The additive label semantics and `add_to_inbox` inheritance question (should children inherit the flag from parents?) must be decided before coding. Recommendation from FEATURES.md and ARCHITECTURE.md: YES, inherit `add_to_inbox` through the parent chain. Validate this decision before writing the resolution logic.
- **Phase 5 (Workflow Wiring):** The deduplication strategy for multi-label emails in `_collect_triaged()` needs an explicit decision: keep `(email_id, label_name)` tuples for conflict detection; deduplicate only for `Email/get` calls.
- **Phase 6 (Re-Triage):** The sweep scope decision — sweep only triggering emails (emails with the new triage label) vs. ALL sender emails from old destination — is architecturally significant. ARCHITECTURE.md recommends: sweep emails from old destination mailbox (bounded by `old_dest_mailbox_id, sender=sender`), not all sender emails ever. Confirm before building.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Full codebase inspected; RFC 8620/8621 verified; no new dependencies is confirmed by source-level analysis, not assumption |
| Features | HIGH | All 5 features derived from explicit pending todos and milestone spec; dependency graph is complete; v1.1 pipeline behavior confirmed by live code |
| Architecture | HIGH | Every relevant source file directly inspected; proposed changes are surgical extensions of proven patterns; to-be architecture diagram derived from as-is code reading |
| Pitfalls | HIGH | CardDAV atomicity is a structural protocol limitation (RFC 6352 confirmed); pydantic v2 optional field semantics confirmed against docs; JMAP per-method error isolation confirmed by RFC 8620 Section 3.4 |

**Overall confidence:** HIGH

### Gaps to Address

- **`add_to_inbox` inheritance decision:** Research recommends YES (inherit through parent chain) but marks it as an open question. This must be decided and locked before Phase 2 begins. The resolution logic for `add_to_inbox` propagation diverges significantly based on this choice.
- **Re-triage sweep scope:** ARCHITECTURE.md recommends sweeping from old destination mailbox only (not all sender emails). FEATURES.md recommends sweeping ALL emails with the old triage label from ANY mailbox. These are consistent but need explicit reconciliation in the Phase 6 design: "sweep `inMailbox: <old_dest_id>, from: <sender>`" is the right scope, not "all sender emails ever."
- **Human test for re-triage:** Noted as a P2 differentiator (add after validation). Given the complexity and risk of re-triage, this should be planned alongside Phase 6, not as an afterthought. It requires setup/teardown against real Fastmail contacts — scope that effort before Phase 6 is sized.
- **Sieve guidance update for additive semantics:** `sieve_guidance.py` output changes when children have their own groups (not inherited). ARCHITECTURE.md notes it may need updating. Verify and update in Phase 2 or Phase 5 when the resolved category shape is final.
- **`provisioner.py` impact:** Features 1 and 2 change what `required_mailboxes` and `contact_groups` produce. The provisioner reads these. Verify the provisioner correctly handles the new independent-child semantics (each child category now gets its own mailbox and group) during Phase 2.

## Sources

### Primary (HIGH confidence)
- Mailroom codebase — `src/mailroom/core/config.py`, `src/mailroom/workflows/screener.py`, `src/mailroom/clients/jmap.py`, `src/mailroom/clients/carddav.py`, `src/mailroom/__main__.py` (directly inspected, current v1.1 state)
- `pyproject.toml` — actual dependency list confirming no new deps needed; `requests` orphan confirmed by source grep
- `.planning/todos/pending/` — all 5 feature todo files (explicit design specs, HIGH confidence)
- `.planning/PROJECT.md` — v1.2 milestone spec and pre-v1.2 research notes
- `.planning/milestones/v1.1-research/` — v1.1 stack and architecture decisions (carry-forward baseline)
- [RFC 8620](https://www.rfc-editor.org/rfc/rfc8620) — JMAP Core: method call batching (Section 3.1), method-level error isolation (Section 3.4), result references (Section 5)
- [RFC 8621](https://www.rfc-editor.org/rfc/rfc8621) — JMAP Email: `Email/query` filter spec, `inMailbox` (single ID), Section 4.4.1
- [RFC 6352](https://www.rfc-editor.org/rfc/rfc6352) — CardDAV: no transaction semantics for multi-resource operations
- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — `Optional[T]` field semantics in pydantic v2

### Secondary (MEDIUM confidence)
- [rcmcarddav group documentation](https://github.com/mstilkerich/rcmcarddav/blob/master/doc/GROUPS.md) — VCard-type group mutation mechanics (separate PUT per group, no cross-group atomicity)
- v1.1 PITFALLS.md and MILESTONE-AUDIT.md — patterns for config migration and derived property pitfalls, applied to v1.2 scope

---
*Research completed: 2026-03-02*
*Ready for roadmap: yes*
