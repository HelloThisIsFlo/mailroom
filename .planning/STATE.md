---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Triage Pipeline v2
status: defining_requirements
last_updated: "2026-03-02"
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** One label tap on a phone triages an entire sender -- all their backlogged emails move to the right place, and all future emails are auto-routed.
**Current focus:** v1.2 Triage Pipeline v2

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-02 — Milestone v1.2 started

## Accumulated Context

### Decisions

Full decision log with outcomes in PROJECT.md Key Decisions table.
v1.1 decisions archived to milestones/v1.1-ROADMAP.md.

### Pending Todos

4. Scan for action labels beyond screener mailbox (area: api) -- IN SCOPE v1.2
5. Sweep workflow: re-label archived emails by contact group membership (area: general) -- far-future idea
7. Migrate to JMAP Contacts API and add programmatic sieve rules (area: api) -- future milestone
11. Allow contact group reassignment via triage label (area: api) -- IN SCOPE v1.2
12. Deploy Grafana + Loki observability stack (area: deployment) -- deferred to v1.3
14. Resolve v1.1 tech debt carry-forward in v1.2 (area: general) -- IN SCOPE v1.2
15. Separate inbox flag from destination mailbox in category config (area: api) -- IN SCOPE v1.2
16. Change parent inheritance to additive label propagation (area: api) -- IN SCOPE v1.2

### Pre-v1.2 Research

JMAP labels are mailboxes. Scanning for triage labels = querying label mailbox IDs directly.
JMAP batched calls allow all label queries in one HTTP round-trip.
Benchmark script: `.research/triage-label-scan/batched_vs_sequential.py`

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-03-02
Stopped at: Milestone v1.2 started — defining requirements
Resume file: N/A
