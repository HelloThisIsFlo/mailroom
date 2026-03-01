# Roadmap: Mailroom

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-02-25)
- 🚧 **v1.1 Push & Config** — Phases 6-9 (in progress)

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
- [ ] **Phase 9: Tech Debt Cleanup** — Fix stale human tests, sync deployment artifacts, remove dead code, deduplicate helpers

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
**Plans**: 3 plans

Plans:
- [x] 08-01-PLAN.md — TDD: Config additions (debounce_seconds, poll_interval default), JMAPClient eventSourceUrl, SSE listener function with reconnection/backoff, drain_queue helper
- [x] 08-02-PLAN.md — Wire SSE into main loop (queue-based debounce), health endpoint SSE status, trigger logging, human integration test
- [ ] 08-03-PLAN.md — Gap closure: prompt shutdown, health trigger field, fast SSE tests, human test rewrite

### Phase 9: Tech Debt Cleanup
**Goal**: All tech debt from the v1.1 milestone audit is resolved — human tests run cleanly against current APIs, deployment artifacts reflect current config schema, and dead/duplicated code is removed
**Depends on**: Phase 8
**Requirements**: None (all v1.1 requirements already satisfied; this closes audit tech debt)
**Gap Closure:** Closes tech debt items from v1.1 milestone audit
**Success Criteria** (what must be TRUE):
  1. Human tests 3, 7-12 run without `AttributeError` — all references to `label_to_group_mapping` and `label_to_imbox` updated to current API
  2. `.env.example` shows `MAILROOM_TRIAGE_CATEGORIES` JSON config instead of 9 deleted individual label/group vars, `POLL_INTERVAL` defaults to 60, and `DEBOUNCE_SECONDS` is documented
  3. `k8s/configmap.yaml` matches `.env.example` — no stale env vars, correct defaults
  4. `JMAPClient.session_capabilities` property and its tests are removed (unused, descoped)
  5. ANSI color helpers extracted into a shared module used by both `reporting.py` and `sieve_guidance.py`
**Plans**: 2 plans

Plans:
- [ ] 09-01-PLAN.md — Human test API migration, deployment artifact sync, dead code removal (session_capabilities)
- [ ] 09-02-PLAN.md — ANSI color helper extraction into shared module with tests

## Progress

**Execution Order:**
Phases execute in numeric order: 6 → 7 → 8 → 9

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
| 8. EventSource Push | v1.1 | 2/3 | In Progress | - |
| 9. Tech Debt Cleanup | v1.1 | 0/2 | Planned | - |

### Phase 09.1: Migrate from env var config to config.yaml (INSERTED)

**Goal:** Replace MAILROOM_-prefixed environment variables with a config.yaml file as the primary configuration mechanism for all non-secret settings, with nested sub-models by concern area and name-only shorthand for triage categories
**Depends on:** Phase 9
**Requirements**: None (inserted phase, no formal requirement IDs)
**Success Criteria** (what must be TRUE):
  1. MailroomSettings loads non-secret config from config.yaml via pydantic-settings YamlConfigSettingsSource
  2. Auth credentials (3 env vars) still work as flat env vars with MAILROOM_ prefix
  3. All source code, tests, and human tests use nested config paths (settings.polling.interval, settings.labels.mailroom_error, etc.)
  4. K8s ConfigMap contains embedded config.yaml file content; Deployment uses volume mount
  5. Missing config.yaml fails fast with clear error message pointing to config.yaml.example
  6. Name-only shorthand works in YAML triage categories (e.g., `- Feed`)
**Plans**: 4 plans

Plans:
- [ ] 09.1-01-PLAN.md — TDD: Config model rewrite with nested sub-models, YAML loading, test infrastructure, example files
- [ ] 09.1-02-PLAN.md — Source code access path migration + K8s artifact updates
- [ ] 09.1-03-PLAN.md — Test file migration (screener, provisioner, sieve guidance, eventsource, logging)
- [ ] 09.1-04-PLAN.md — Human test migration + committable config.yaml
