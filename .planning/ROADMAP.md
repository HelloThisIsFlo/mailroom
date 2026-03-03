# Roadmap: Mailroom

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-02-25)
- ✅ **v1.1 Push & Config** — Phases 6-9 (shipped 2026-03-02)
- 🚧 **v1.2 Triage Pipeline v2** — Phases 10-13 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-02-25</summary>

- [x] Phase 1: Foundation and JMAP Client (3/3 plans) — completed 2026-02-24
- [x] Phase 2: CardDAV Client, Validation Gate (3/3 plans) — completed 2026-02-24
- [x] Phase 3: Triage Pipeline (3/3 plans) — completed 2026-02-24
- [x] Phase 3.1: Person Contact Type with @ToPerson Label (3/3 plans, INSERTED) — completed 2026-02-25
- [x] Phase 4: Packaging and Deployment (3/3 plans) — completed 2026-02-25
- [x] Phase 5: Documentation and Showcase (3/3 plans) — completed 2026-02-25

Full details: `milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v1.1 Push & Config (Phases 6-9) — SHIPPED 2026-03-02</summary>

- [x] Phase 6: Configurable Categories (2/2 plans) — completed 2026-02-26
- [x] Phase 7: Setup Script (4/4 plans) — completed 2026-02-27
- [x] Phase 8: EventSource Push (3/3 plans) — completed 2026-02-27
- [x] Phase 9: Tech Debt Cleanup (2/2 plans) — completed 2026-02-28
- [x] Phase 9.1: Migrate to config.yaml (5/5 plans, INSERTED) — completed 2026-03-01
- [x] Phase 9.1.1: Helm Chart Migration (2/2 plans, INSERTED) — completed 2026-03-02

Full details: `milestones/v1.1-ROADMAP.md`

</details>

### 🚧 v1.2 Triage Pipeline v2 (In Progress)

**Milestone Goal:** Evolve the triage pipeline -- independent config axes (inbox flag, additive parent labels), label-based scanning beyond Screener, and re-triage support for moving senders between groups.

- [x] **Phase 10: Tech Debt Cleanup** - Close v1.1 carry-forward items and expose public interfaces needed by config refactor (completed 2026-03-02)
- [x] **Phase 11: Config Layer** - Separate inbox flag, make children fully independent categories with additive parent labels (completed 2026-03-02)
- [ ] **Phase 12: Label Scanning** - Scan for triage labels via label mailbox queries with batched JMAP requests
- [ ] **Phase 13: Re-triage** - Move senders between contact groups with email re-filing and triage history

## Phase Details

### Phase 10: Tech Debt Cleanup
**Goal**: v1.1 audit is fully closed and public interfaces are ready for config refactor
**Depends on**: Nothing (first phase of v1.2)
**Requirements**: DEBT-01, DEBT-02, DEBT-03, DEBT-04, DEBT-05
**Success Criteria** (what must be TRUE):
  1. `MailroomSettings.resolved_categories` is a public property usable by any module without accessing private attributes
  2. `sieve_guidance.py` generates correct output using only the public `resolved_categories` interface
  3. `test_13_docker_polling.py` passes poll interval via config.yaml mount and the interval is actually respected
  4. `conftest.py` cleanup list contains only env var names that exist in current `MailroomSettings`
  5. Phase 09.1.1 has a VERIFICATION.md that documents its UAT results
**Plans**: 2 plans

Plans:
- [ ] 10-01-PLAN.md — Public resolved_categories property, sieve_guidance update, Docker test fix, conftest cleanup
- [ ] 10-02-PLAN.md — Write retroactive VERIFICATION.md for Phase 09.1.1

### Phase 11: Config Layer
**Goal**: Operators can configure inbox visibility independently of destination mailbox, and child categories resolve as fully independent categories that additively carry parent labels
**Depends on**: Phase 10
**Requirements**: CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, CFG-06, CFG-07, CFG-08
**Success Criteria** (what must be TRUE):
  1. A category with `add_to_inbox: true` files emails to its destination mailbox AND adds them to Inbox; a category without the flag files only to its destination (Inbox visibility is independent of destination)
  2. A child category has its own label, contact group, and destination mailbox derived from its name -- it does not inherit these fields from its parent
  3. Triaging a sender with a child category applies both the child's label and the parent's label chain (additive propagation, not field inheritance)
  4. Circular parent references and `destination_mailbox: Inbox` are rejected at startup with clear error messages
  5. Setup CLI provisions separate mailboxes and contact groups for each child category, and sieve guidance reflects additive label semantics
**Plans**: 4 plans

Plans:
- [ ] 11-01-PLAN.md — Config models, defaults, validation, resolution (add_to_inbox, independent children, CFG-02, parent chain)
- [ ] 11-02-PLAN.md — Screener workflow additive filing and additive contact groups
- [ ] 11-03-PLAN.md — Sieve guidance all-category display, syntax highlighting, config.yaml.example
- [ ] 11-04-PLAN.md — Gap closure: CFG-02 case-insensitive Inbox rejection, remove --ui-guide and sieve clutter

### Phase 12: Label Scanning
**Goal**: Triage pipeline discovers labeled emails by querying label mailboxes directly, scanning beyond the Screener mailbox with batched JMAP requests
**Depends on**: Phase 11
**Requirements**: SCAN-01, SCAN-02, SCAN-03
**Success Criteria** (what must be TRUE):
  1. Emails with triage labels are discovered regardless of which mailbox they reside in (not limited to Screener)
  2. All label mailbox queries execute in a single JMAP HTTP round-trip (batched request)
  3. A per-method error in a batched JMAP response is detected and logged, not silently dropped
**Plans**: TBD

Plans:
- [ ] 12-01: TBD

### Phase 13: Re-triage
**Goal**: Applying a triage label to an already-grouped sender moves them to the new group with email re-filing and auditable triage history
**Depends on**: Phase 12
**Requirements**: RTRI-01, RTRI-02, RTRI-03, RTRI-04, RTRI-05, RTRI-06
**Success Criteria** (what must be TRUE):
  1. Applying a triage label to a sender who is already in a contact group moves them to the new group (add-to-new first, then remove-from-old)
  2. Re-triaged sender's emails are re-filed by fetching ALL emails from the contact (any mailbox) and applying new additive labels (child + parent chain destinations)
  3. Contact note captures triage history with dates -- both initial "Added to [group]" and subsequent "Moved from [old] to [new]" entries
  4. Re-triage is logged as a `group_reassigned` structured event with old and new group names
  5. A human integration test validates the full re-triage workflow end-to-end against live Fastmail
  6. `add_to_inbox` only adds Inbox label to emails from Screener -- re-triage does NOT re-add Inbox to existing emails
**Note**: Sweep logic decisions captured in `docs/WIP.md` during Phase 11 discussion. Key: sweep fetches all emails from contact, applies additive mailbox labels, add_to_inbox is Screener-only.
**Plans**: TBD

Plans:
- [ ] 13-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 10 -> 11 -> 12 -> 13

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 10. Tech Debt Cleanup | 2/2 | Complete    | 2026-03-02 | - |
| 11. Config Layer | 4/4 | Complete   | 2026-03-03 | - |
| 12. Label Scanning | v1.2 | 0/? | Not started | - |
| 13. Re-triage | v1.2 | 0/? | Not started | - |
