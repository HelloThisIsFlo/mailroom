---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Triage Pipeline v2
status: completed
stopped_at: Completed 15-02-PLAN.md (v1.2 milestone complete)
last_updated: "2026-03-05T00:38:05.848Z"
last_activity: "2026-03-05 - Completed 15-02: Documentation finalization"
progress:
  total_phases: 6
  completed_phases: 6
  total_plans: 18
  completed_plans: 18
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** One label tap on a phone triages an entire sender -- all their backlogged emails move to the right place, and all future emails are auto-routed.
**Current focus:** v1.2 Milestone Complete

## Current Position

Phase: 15 (Milestone Closeout & Cleanup) -- sixth of 6 phases
Plan: 2 of 2 (all plans complete)
Status: All Plans Complete
Last activity: 2026-03-05 - Completed 15-02: Documentation finalization

Progress: [██████████] 100% (2 of 2 plans complete in Phase 15)

## Performance Metrics

**Velocity:**
- Total plans completed: 18 (v1.2)
- Average duration: 5min
- Total execution time: 93min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 10-tech-debt-cleanup | 2 | 3min | 2min |
| 11-config-layer | 4 | 22min | 6min |
| 12-label-scanning | 1 | 8min | 8min |
| 13-re-triage | 3 | 21min | 7min |
| 14-contact-provenance | 5 | 32min | 6min |
| 15-milestone-closeout | 2 | 7min | 4min |

*Updated after each plan completion*
| Phase 15 P01 | 3min | 2 tasks | 7 files |
| Phase 15 P02 | 4min | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Full decision log with outcomes in PROJECT.md Key Decisions table.
v1.1 decisions archived to milestones/v1.1-ROADMAP.md.

Recent decisions for v1.2:
- `add_to_inbox` does NOT inherit through parent chain (explicit per category only)
- No backward compatibility -- config supports current format only
- Re-triage has no `@MailroomWarning` -- it is a normal supported operation
- Contact notes capture triage history (added/moved with dates)
- CardDAV group reassignment order: add-to-new FIRST, then remove-from-old (safe partial-failure order)
- [10-02] Used 2026-03-02T00:00:00Z as retroactive verification date for 09.1.1 VERIFICATION.md
- [10-01] resolved_categories returns list() copy, consistent with existing label_to_category_mapping pattern
- [10-01] Internal properties keep using _resolved_categories directly (internal to class)
- [11-01] Imbox uses add_to_inbox=True with derived destination_mailbox="Imbox" (not "Inbox")
- [11-01] Children are fully independent: Person has contact_group="Person", destination_mailbox="Person"
- [11-01] CFG-02 rejects destination_mailbox: Inbox at validation time with helpful error
- [11-02] No refactor phase needed -- additive chain implementation is clean and self-contained
- [11-03] Removed _highlight_folder -- all mailbox names get unconditional CYAN highlighting
- [11-03] Prominent IMPORTANT note at top of sieve guidance about "Continue to apply other rules"
- [11-04] Case-insensitive Inbox check uses resolved_mailbox.lower() == "inbox" (single comparison point)
- [11-04] Kept informational jmapquery mention in sieve guidance intro (explains why UI creation is needed)
- [12-01] Error filtering stays as separate jmap.call() after batch -- cannot batch without result references
- [12-01] Escalation threshold: 3 consecutive failures before ERROR level (~3 minutes at 60s poll interval)
- [12-01] Pagination via follow-up query_emails() for labels with total > len(ids)
- [13-01] create_contact() requires group_name as keyword-only arg for triage history note
- [13-01] Triage history uses em-dash Mailroom header for programmatic detection
- [13-01] Old-format notes preserved as historical context above Mailroom section
- [13-01] get_email_mailbox_ids returns sets for O(1) membership checks
- [13-02] Re-triage replaces already-grouped error path (no @MailroomError for grouped senders)
- [13-02] Same-group re-triage runs full reconciliation for self-healing
- [13-02] Chain diff uses set operations on contact_group names
- [13-02] Inbox explicitly excluded from managed label removal set
- [13-03] JMAP pagination uses len-based check instead of total field (total requires calculateTotal: true)
- [Phase 14]: MailroomSectionSettings replaces LabelSettings with field renames: mailroom_error->label_error, mailroom_warning->label_warning
- [Phase 14]: Provenance group tracked as kind=mailroom in provisioner (infrastructure, not triage)
- [Phase 14]: apply_resources routes non-@ mailroom resources through carddav.create_group
- [Phase 14]: infrastructure_groups stored as set on CardDAVClient, populated via validate_groups param
- [Phase 14]: Provenance note: Created by Mailroom for new, Adopted by Mailroom for existing without prior note
- [Phase 14]: Warning cleanup-then-reapply: remove @MailroomWarning before processing, reapply if condition persists
- [Phase 14]: User-modified detection checks vCard fields beyond Mailroom's managed set (version, uid, fn, n, email, note, org, prodid)
- [Phase 14]: 7-step reset order: labels, system-label cleanup, group removal, warning application, provenance removal, note strip, contact delete
- [14-04]: Step 1 adds Screener before removing managed labels (atomic move pattern for RFC 8621 compliance)
- [14-04]: Step 6 skips contacts_to_delete entirely (don't modify resources about to be deleted)
- [Phase 14]: Config error for old labels key uses plain unknown-key rejection with valid keys list
- [Phase 14]: REV field exclusion from MAILROOM_MANAGED_FIELDS documented as relied-upon Fastmail behavior
- [14-06]: Reset --apply confirmation default [y/N] declines on Enter (safe default for destructive ops)
- [14-06]: Non-interactive stdin aborts with explicit message, not silent failure
- [15-01]: Replaced batch_move_emails.assert_not_called() with jmap.call.assert_not_called() after removing dead method
- [15-01]: Updated RTRI-04 wording to match actual code: "Triaged to" / "Re-triaged to"
- [15-02]: Split architecture.md into two mermaid diagrams (triage flow + category hierarchy) for clarity
- [15-02]: Did NOT update docs/index.html (marketing page, out of scope for cleanup phase)
- [15-02]: config.md full example reproduces config.yaml.example verbatim

### Pending Todos

7. Migrate to JMAP Contacts API and add programmatic sieve rules (area: api) -- future milestone
12. Deploy Grafana + Loki observability stack (area: deployment) -- deferred to v1.3

### Roadmap Evolution

- Phase 14 added: Contact provenance tracking for clean reset
- Phase 15 added: Milestone closeout and cleanup

### Blockers/Concerns

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 1 | Add a mailroom reset CLI command that undoes all mailroom changes (contacts, labels, groups) with dry-run/apply mode | 2026-03-04 | a754f75 | Verified | [1-add-a-mailroom-reset-cli-command-that-un](./quick/1-add-a-mailroom-reset-cli-command-that-un/) |

## Session Continuity

Last session: 2026-03-05T00:32:53Z
Stopped at: Completed 15-02-PLAN.md (v1.2 milestone complete)
Resume file: N/A (all plans complete)
