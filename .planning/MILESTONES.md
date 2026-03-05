# Milestones

## v1.2 Triage Pipeline v2 (Shipped: 2026-03-05)

**Delivered:** Evolved triage pipeline with independent config axes, batched label scanning beyond Screener, re-triage support for moving senders between groups, contact provenance tracking for clean reset, and full documentation.

**Stats:** 6 phases, 18 plans | 15,765 LOC Python | 407 tests + 18 human integration tests | 228 files changed | 3 days | 150 commits

**Git range:** Phase 10 → Phase 15 | Tag: `v1.2`

**Key accomplishments:**
- Resolved v1.1 tech debt — public resolved_categories API, Docker test fix, conftest cleanup
- Independent config axes — add_to_inbox flag, 7 default categories, additive parent chain filing
- Batched label scanning — single JMAP round-trip for all label mailbox queries with escalating error handling
- Full re-triage pipeline — group reassignment via chain diff, email label reconciliation, human integration test against live Fastmail
- Contact provenance tracking — created/adopted distinction, provenance-aware reset with 3-way classification (delete/warn/strip) and confirmation gate
- Documentation finalization — workflow.md, config.md, architecture.md with mermaid diagrams

**Inserted phases (beyond original scope):**
- Phase 14: Contact provenance tracking for clean reset (added during v1.2)
- Phase 15: Milestone closeout and cleanup (gap closure from audit)

**Tech debt:** None — all items from v1.1 carry-forward resolved in Phase 10, all audit gaps closed by Phase 15.

**Archives:** `milestones/v1.2-ROADMAP.md`, `milestones/v1.2-REQUIREMENTS.md`, `milestones/v1.2-MILESTONE-AUDIT.md`

---

## v1.1 Push & Config (Shipped: 2026-03-02)

**Delivered:** Configurable triage categories, automated Fastmail setup, sub-10-second push notifications via JMAP EventSource, config.yaml migration, and Helm chart deployment.

**Stats:** 6 phases (2 inserted), 18 plans | 12,572 LOC Python | 278 tests + 16 human integration tests | 46 files | 5 days | 140 commits

**Git range:** `feat(06-01)` → `chore(helm)` | Tag: `v1.1`

**Key accomplishments:**
- Configurable triage categories via structured TriageCategory model with zero-config defaults matching v1.0
- Idempotent setup CLI with plan/apply pattern provisions mailboxes and contact groups on Fastmail
- JMAP EventSource push notifications replace 5-minute polling with sub-10-second triage latency
- Human tests migrated to current APIs, deployment artifacts synced, ANSI color helpers extracted to shared module
- Config.yaml replaces 18 env vars with nested YAML via pydantic-settings; name-only shorthand for categories
- Helm chart replaces plain k8s manifests with secrets-values.yaml pattern and setup Job preflight

**Inserted phases (beyond original scope):**
- Phase 9.1: Config.yaml migration — replaced env vars with YAML config
- Phase 9.1.1: Helm chart migration with vanilla patterns

**Tech debt (carry-forward to v1.2):**
- Phase 09.1.1 missing VERIFICATION.md (UAT 8/8 passed, no formal requirements)
- test_13_docker_polling.py: MAILROOM_POLL_INTERVAL env var silently ignored (config.yaml is now config source)
- sieve_guidance.py: accesses private `_resolved_categories` — needs public property
- conftest.py: stale env var cleanup list (7 vars no longer in MailroomSettings)

**Archives:** `milestones/v1.1-ROADMAP.md`, `milestones/v1.1-REQUIREMENTS.md`, `milestones/v1.1-MILESTONE-AUDIT.md`

---

## v1.0 MVP (Shipped: 2026-02-25)

**Delivered:** HEY Mail's Screener workflow on Fastmail — one label tap triages an entire sender, sweeps their backlog, and auto-routes future emails.

**Stats:** 6 phases, 18 plans | 8,666 LOC Python | 180 tests + 13 human integration tests | 122 files | 3 days

**Git range:** `feat(01-01)` → `feat(05-01)` | Tag: `v1.0`

**Key accomplishments:**
- JMAP client with session discovery, mailbox resolution, email query/move/relabel, and batch chunking
- CardDAV client with contact search/create/group membership, ETag conflict handling, validated against live Fastmail
- Screener triage pipeline: poll → conflict detect → upsert contact → sweep emails → remove triage label, with retry safety
- Person/company contact types via @ToPerson label with nameparser, @MailroomWarning for name mismatches
- Docker + k8s deployment: multi-stage build, k8s manifests (namespace, configmap, secret, deployment), GitHub Actions CI, health endpoint
- Documentation: README, deployment guide, architecture docs, animated product showcase page

**Bonus deliveries (beyond v1 requirements):**
- TRIAGE-11 (sender display name preservation) — delivered in Phase 3
- OPS-02 (health/liveness probe) — delivered in Phase 4
- Phase 3.1 (person/company contact types) — inserted phase beyond original scope

**Tech debt (Info severity):**
- REQUIREMENTS.md traceability missing Phase 3.1 extensions (doc gap only)
- Duplicate "Inbox" in required_mailboxes (functionally harmless)
- Latent KeyError in _apply_warning_label (guarded by call site, not reachable)
- SUMMARY.md files lack requirements-completed frontmatter

**Archives:** `milestones/v1.0-ROADMAP.md`, `milestones/v1.0-REQUIREMENTS.md`, `milestones/v1.0-MILESTONE-AUDIT.md`

---

