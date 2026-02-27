# Roadmap: Mailroom

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-02-25)
- 🚧 **v1.1 Push & Config** — Phases 6-8 (in progress)

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

### 🚧 v1.1 Push & Config (In Progress)

**Milestone Goal:** Replace polling with push notifications, make triage categories user-configurable, and add automated Fastmail setup.

- [ ] **Phase 6: Configurable Categories** — Structured triage category mapping replaces hardcoded config; all derived properties computed from categories
- [ ] **Phase 7: Setup Script** — Idempotent CLI provisions required mailboxes and contact groups on Fastmail with dry-run safety
- [ ] **Phase 8: EventSource Push** — SSE listener replaces fixed-interval polling with sub-10-second push-triggered triage

## Phase Details

### Phase 6: Configurable Categories
**Goal**: Users can define and customize their triage categories through a single structured configuration, and the service derives all behavior from that mapping
**Depends on**: Phase 5 (v1.0 complete)
**Requirements**: CONFIG-01, CONFIG-02, CONFIG-03, CONFIG-04, CONFIG-05, CONFIG-06
**Success Criteria** (what must be TRUE):
  1. User can deploy with zero config and get the same 5 default categories as v1.0 (Imbox, Feed, PaperTrail, Jail, Person)
  2. User can define a custom triage category (e.g., "Receipts") via `MAILROOM_TRIAGE_CATEGORIES` JSON env var and it works end-to-end: label detected, contact grouped, emails swept to destination
  3. Service rejects invalid category configurations at startup with a clear error message (missing fields, duplicate labels)
  4. All triage labels, contact groups, and required mailboxes are computed from the category list -- no hardcoded references remain in service logic
**Plans**: 2 plans

Plans:
- [ ] 06-01-PLAN.md — TDD: TriageCategory model, ResolvedCategory, derivation rules, defaults, and validation
- [ ] 06-02-PLAN.md — Integrate triage_categories into MailroomSettings, update consumers and tests

### Phase 7: Setup Script
**Goal**: Users can run a single command to provision all required Fastmail resources for their configured categories, with clear guidance for the one manual step (sieve rules)
**Depends on**: Phase 6
**Requirements**: SETUP-01, SETUP-02, SETUP-03, SETUP-04, SETUP-05, SETUP-06
**Success Criteria** (what must be TRUE):
  1. User runs `mailroom-setup --apply` and all missing triage label mailboxes and contact groups are created on Fastmail
  2. User runs `mailroom-setup` (no flag) and sees what would be created without any changes made to Fastmail
  3. User runs `mailroom-setup --apply` a second time and sees "already exists" for every item -- no duplicates, no errors
  4. Setup output includes human-readable sieve rule instructions that the user can follow to complete email routing
  5. Setup script reads the same `MAILROOM_TRIAGE_CATEGORIES` config as the main service -- adding a custom category to config and re-running setup provisions it
**Plans**: 4 plans

Plans:
- [ ] 07-01-PLAN.md — Click CLI framework, JMAPClient.create_mailbox(), CardDAVClient.create_group()
- [ ] 07-02-PLAN.md — Provisioner with plan/apply pattern, reporting, and resource categorization
- [ ] 07-03-PLAN.md — Sieve rule guidance (no introspection) and human integration tests
- [ ] 07-04-PLAN.md — Gap closure: output coloring, 4 resource categories, override name highlighting

### Phase 8: EventSource Push
**Goal**: Triage latency drops from up to 5 minutes to under 10 seconds via JMAP EventSource push, with automatic fallback to polling if the SSE connection fails
**Depends on**: Phase 6
**Requirements**: PUSH-01, PUSH-02, PUSH-03, PUSH-04, PUSH-05, PUSH-06
**Success Criteria** (what must be TRUE):
  1. User applies a triage label on their phone and the email is triaged within 10 seconds (vs. up to 5 minutes with polling)
  2. If the SSE connection drops, the service auto-reconnects with exponential backoff and resumes push-triggered triage without user intervention
  3. If the SSE connection is dead or unavailable, the service falls back to polling at the configured interval -- triage never stops
  4. Health endpoint reports EventSource connection status and SSE thread liveness so the user can monitor push health via k8s
**Plans**: 2 plans

Plans:
- [ ] 08-01-PLAN.md — TDD: Config additions (debounce_seconds, poll_interval default), JMAPClient eventSourceUrl, SSE listener function with reconnection/backoff, drain_queue helper
- [ ] 08-02-PLAN.md — Wire SSE into main loop (queue-based debounce), health endpoint SSE status, trigger logging, human integration test

## Progress

**Execution Order:**
Phases execute in numeric order: 6 → 7 → 8

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation and JMAP Client | v1.0 | 3/3 | Complete | 2026-02-24 |
| 2. CardDAV Client (Validation Gate) | v1.0 | 3/3 | Complete | 2026-02-24 |
| 3. Triage Pipeline | v1.0 | 3/3 | Complete | 2026-02-24 |
| 3.1. Person Contact Type (@ToPerson) | v1.0 | 3/3 | Complete | 2026-02-25 |
| 4. Packaging and Deployment | v1.0 | 3/3 | Complete | 2026-02-25 |
| 5. Documentation and Showcase | v1.0 | 3/3 | Complete | 2026-02-25 |
| 6. Configurable Categories | v1.1 | 0/2 | Planned | - |
| 7. Setup Script | v1.1 | 0/3 | Planned | - |
| 8. EventSource Push | v1.1 | 0/? | Not started | - |
