---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Triage Pipeline v2
status: completed
stopped_at: Completed 14-06-PLAN.md
last_updated: "2026-03-04T20:18:18.830Z"
last_activity: "2026-03-04 - Completed 14-06: Reset --apply confirmation prompt"
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 16
  completed_plans: 16
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** One label tap on a phone triages an entire sender -- all their backlogged emails move to the right place, and all future emails are auto-routed.
**Current focus:** Phase 14 - Contact provenance tracking for clean reset

## Current Position

Phase: 14 (Contact Provenance Tracking) -- fifth of 5 phases
Plan: 6 of 6 (all gap closure plans complete)
Status: All Plans Complete
Last activity: 2026-03-04 - Completed 14-06: Reset --apply confirmation prompt

Progress: [██████████] 100% (6 plans complete in Phase 14, including gap closure)

## Performance Metrics

**Velocity:**
- Total plans completed: 15 (v1.2)
- Average duration: 6min
- Total execution time: 86min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 10-tech-debt-cleanup | 2 | 3min | 2min |
| 11-config-layer | 4 | 22min | 6min |
| 12-label-scanning | 1 | 8min | 8min |
| 13-re-triage | 3 | 21min | 7min |
| 14-contact-provenance | 5 | 32min | 6min |

*Updated after each plan completion*
| Phase 14 P02 | 11min | 2 tasks | 5 files |
| Phase 14 P03 | 7min | 2 tasks | 7 files |
| Phase 14 P04 | 4min | 2 tasks | 2 files |
| Phase 14 P05 | 3min | 2 tasks | 6 files |
| Phase 14 P06 | 4min | 1 task | 3 files |

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

### Pending Todos

5. Sweep workflow: re-label archived emails by contact group membership (area: general) -- far-future idea
7. Migrate to JMAP Contacts API and add programmatic sieve rules (area: api) -- future milestone
12. Deploy Grafana + Loki observability stack (area: deployment) -- deferred to v1.3

### Roadmap Evolution

- Phase 14 added: Contact provenance tracking for clean reset

### Blockers/Concerns

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 1 | Add a mailroom reset CLI command that undoes all mailroom changes (contacts, labels, groups) with dry-run/apply mode | 2026-03-04 | a754f75 | Verified | [1-add-a-mailroom-reset-cli-command-that-un](./quick/1-add-a-mailroom-reset-cli-command-that-un/) |

## Session Continuity

Last session: 2026-03-04T20:10:00Z
Stopped at: Completed 14-06-PLAN.md
Resume file: None
