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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Timeline | Phases | Plans | Key Change |
|-----------|----------|--------|-------|------------|
| v1.0 | 3 days | 6 | 18 | Established TDD + human test pattern |
| v1.1 | 5 days | 6 | 18 | Added quick tasks, inserted phases for urgent work |

### Cumulative Quality

| Milestone | Unit Tests | Human Tests | LOC | Files |
|-----------|-----------|-------------|-----|-------|
| v1.0 | 180 | 13 | 8,666 | 122 |
| v1.1 | 278 | 16 | 12,572 | 46 |

### Top Lessons (Verified Across Milestones)

1. Human integration tests against live APIs are essential — caught issues in both milestones that unit tests missed
2. Inserted phases (decimal numbering) are a reliable pattern for scope additions mid-milestone
3. Validate external API behavior early (CardDAV in v1.0, EventSource in v1.1) before building abstractions
