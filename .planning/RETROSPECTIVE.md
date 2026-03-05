# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-02-25
**Phases:** 6 (1 inserted) | **Plans:** 18 | **Timeline:** 3 days

### What Was Built
- JMAP client with session discovery, mailbox resolution, email query/move/relabel
- CardDAV client with contact search/create/group membership, ETag conflict handling
- Screener triage pipeline with retry safety and backlog sweep
- Person/company contact types via @ToPerson label
- Docker + k8s deployment with CI and health endpoint

### What Worked
- CardDAV validation gate (Phase 2) — testing against live Fastmail early prevented building on wrong assumptions
- TDD with atomic commits — RED/GREEN/REFACTOR kept velocity high and regressions near zero
- Human integration tests against real Fastmail — caught real-world edge cases unit tests missed

### What Was Inefficient
- SUMMARY.md files lacked one-liner frontmatter — made milestone completion harder to automate
- Phase 3.1 was inserted late (person contact types) — could have been scoped from the start

### Patterns Established
- Human tests as first-class citizens alongside unit tests
- Retry safety: triage label removed LAST so failures auto-retry
- Conflict detection: same sender + different labels = @MailroomError

### Key Lessons
1. Validate external API assumptions with live tests before building abstractions
2. Inserted phases work well for bonus features — decimal numbering keeps ordering clear
3. Human integration tests are essential for a single-user tool that talks to real APIs

---

## Milestone: v1.1 — Push & Config

**Shipped:** 2026-03-02
**Phases:** 6 (2 inserted) | **Plans:** 18 | **Timeline:** 5 days | **Commits:** 140

### What Was Built
- Configurable triage categories via TriageCategory model with zero-config defaults
- Idempotent setup CLI with plan/apply pattern for Fastmail provisioning
- JMAP EventSource push with sub-10s triage latency, reconnection, polling fallback
- Tech debt cleanup: API migration, deployment sync, color helper extraction
- Config.yaml replaces 18 env vars with nested YAML via pydantic-settings
- Helm chart replaces plain k8s manifests with secrets-values.yaml pattern

### What Worked
- Build order (Config → Setup → Push → Cleanup) was exactly right — each phase built on the last
- Inserted phases (9.1 config.yaml, 9.1.1 Helm) landed smoothly mid-milestone
- Quick tasks (/gsd:quick) for small changes — JSON log reordering, Helm simplification
- 18/18 requirements fully covered with zero gaps at audit time

### What Was Inefficient
- Helm chart was over-engineered initially with PodSecurity hardening, then simplified in quick-6 — should have started simple
- Phase 9 (tech debt) scoped .env.example and k8s/configmap.yaml updates that were immediately superseded by Phase 9.1
- ROADMAP.md progress table fell out of sync (showed wrong plan counts for some phases)
- 4 tech debt items accumulated that weren't caught until milestone audit

### Patterns Established
- Config.yaml as primary non-secret config, env vars only for auth secrets
- Helm chart with secrets-values.yaml pattern (not committed, provided at deploy time)
- Drain-wait-drain debounce for SSE events
- Queue sentinel for graceful shutdown

### Key Lessons
1. Start Helm charts simple — add complexity only when cluster policy requires it
2. Inserted phases for deployment changes work well but create tech debt in already-executed phases (stale artifacts)
3. Config migration is a high-impact change that touches every file — plan for a dedicated phase
4. Milestone audits before completion catch tech debt that accumulates across phases
5. Quick tasks are excellent for small improvements that don't warrant full phase planning

### Cost Observations
- Model mix: primarily opus for planning/execution, sonnet for research agents
- Sessions: ~15 across 5 days
- Notable: Phase 9.1 (config migration) was the largest phase at 5 plans, touching nearly every file

---

## Milestone: v1.2 — Triage Pipeline v2

**Shipped:** 2026-03-05
**Phases:** 6 (2 added for provenance + closeout) | **Plans:** 18 | **Timeline:** 3 days | **Commits:** 150

### What Was Built
- Independent config axes — `add_to_inbox` flag, 7 default categories, additive parent chain filing
- Batched label scanning — single JMAP round-trip for all label mailbox queries
- Re-triage pipeline — group reassignment, email label reconciliation, triage history
- Contact provenance tracking — created/adopted distinction, provenance-aware reset with 3-way classification
- Documentation finalization — workflow.md, config.md, architecture.md with mermaid diagrams

### What Worked
- Phase discussion (`/gsd:discuss-phase`) before Phase 11 — resolved major design questions (parent inheritance, add_to_inbox semantics) before any code was written
- Milestone audit caught 6 tech debt items + 1 orphaned requirement — Phase 15 closed all gaps cleanly
- TDD pattern continued strong — 407 tests, zero failures, zero cross-contamination after structlog fix
- Gap closure phases (14-04, 14-05, 14-06, 15) were fast and surgical — avg 4min/plan
- Execution velocity: 18 plans in 93 minutes total (~5 min/plan average)

### What Was Inefficient
- Phase 14 needed 3 gap closure plans (14-04, 14-05, 14-06) discovered during UAT — could have been caught earlier with more thorough plan review
- SUMMARY.md one-liner field still null for all files — CLI couldn't auto-extract accomplishments at milestone completion
- `docs/WIP.md` lingered through Phases 11-14 without being finalized — should have been addressed in the phase where decisions stabilized

### Patterns Established
- Additive parent labels — children are independent categories, parents add their labels on top
- Add-to-new-first group reassignment — safe partial-failure order for contact moves
- 7-step reset operation order — deterministic, testable, documented
- Provenance tracking — created vs. adopted contacts enables safe cleanup
- Warning cleanup-then-reapply — remove @MailroomWarning before processing, reapply if condition persists

### Key Lessons
1. Phase discussions before planning prevent expensive mid-phase design pivots — the v1.2 config design was settled before Phase 11 code began
2. Milestone audits are invaluable — `gaps_found` → gap closure phase → `passed` is a reliable quality gate
3. Gap closure plans are fast when the codebase is well-tested — fix is surgical, tests verify immediately
4. Documentation should be finalized in the phase where the feature stabilizes, not deferred to milestone end
5. `add_to_inbox` as explicit-only (no inheritance) was the right call — inheritance would have created confusing cascading behavior

### Cost Observations
- Model mix: opus for planning/execution, sonnet for research, haiku for simple tasks
- Sessions: ~10 across 3 days
- Notable: 93 minutes total execution time for 18 plans — fastest milestone per plan

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Timeline | Phases | Plans | Key Change |
|-----------|----------|--------|-------|------------|
| v1.0 | 3 days | 6 | 18 | Established TDD + human test pattern |
| v1.1 | 5 days | 6 | 18 | Added quick tasks, inserted phases for urgent work |
| v1.2 | 3 days | 6 | 18 | Milestone audit → gap closure loop, phase discussions |

### Cumulative Quality

| Milestone | Unit Tests | Human Tests | LOC | Files |
|-----------|-----------|-------------|-----|-------|
| v1.0 | 180 | 13 | 8,666 | 122 |
| v1.1 | 278 | 16 | 12,572 | 46 |
| v1.2 | 407 | 18 | 15,765 | 228 |

### Execution Velocity

| Milestone | Total Exec Time | Avg per Plan | Plans |
|-----------|-----------------|-------------|-------|
| v1.0 | — | — | 18 |
| v1.1 | — | — | 18 |
| v1.2 | 93 min | 5 min | 18 |

### Top Lessons (Verified Across Milestones)

1. Human integration tests against live APIs are essential — caught issues in all three milestones that unit tests missed
2. Inserted phases (decimal numbering) are a reliable pattern for scope additions mid-milestone
3. Validate external API behavior early (CardDAV in v1.0, EventSource in v1.1, JMAP batch in v1.2) before building abstractions
4. Milestone audits before completion catch accumulated tech debt and orphaned requirements (v1.1, v1.2)
5. Phase discussions resolve design questions before code — prevents expensive mid-phase pivots (v1.2)
