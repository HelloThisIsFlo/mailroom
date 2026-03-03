# Requirements: Mailroom

**Defined:** 2026-03-02
**Core Value:** One label tap on a phone triages an entire sender — all their backlogged emails move to the right place, and all future emails are auto-routed.

## v1.2 Requirements

Requirements for Triage Pipeline v2. Each maps to roadmap phases.

### Tech Debt

- [x] **DEBT-01**: Phase 09.1.1 VERIFICATION.md written to close audit gap
- [x] **DEBT-02**: `resolved_categories` exposed as public property on MailroomSettings
- [x] **DEBT-03**: `sieve_guidance.py` uses public `resolved_categories` interface
- [x] **DEBT-04**: `test_13_docker_polling.py` passes poll interval via config.yaml mount
- [x] **DEBT-05**: Stale env var names removed from `conftest.py` cleanup list

### Config

- [x] **CFG-01**: Operator can set `add_to_inbox` per category to control Inbox visibility independently of destination mailbox (does not inherit through parent chain)
- [x] **CFG-02**: System rejects `destination_mailbox: Inbox` with clear error pointing to `add_to_inbox` flag
- [x] **CFG-03**: Child categories resolve as fully independent categories (own label, contact group, destination mailbox derived from name)
- [x] **CFG-04**: Parent relationship applies parent's label chain on triage (additive labels, not field inheritance)
- [x] **CFG-05**: Circular parent references detected and rejected at startup validation
- [x] **CFG-06**: No backward compatibility — config supports current format only, no migration shims or legacy fallbacks
- [x] **CFG-07**: Setup CLI provisions independent mailbox and contact group for each child category
- [x] **CFG-08**: Sieve guidance output reflects additive parent label semantics

### Scanning

- [x] **SCAN-01**: Triage labels discovered by querying label mailbox IDs directly (not limited to Screener mailbox)
- [x] **SCAN-02**: All label mailbox queries batched into single JMAP HTTP request
- [x] **SCAN-03**: Per-method errors in batched JMAP responses detected and handled (not silently dropped)

### Re-triage

- [x] **RTRI-01**: Applying a triage label to an already-grouped sender moves them to the new contact group
- [x] **RTRI-02**: Re-triaged sender's emails re-filed by fetching ALL emails from the contact (any mailbox, not just Screener) and applying the new additive mailbox labels (child + parent chain)
- [ ] **RTRI-03**: Re-triage logged as `group_reassigned` structured event with old and new group names
- [x] **RTRI-04**: Contact note captures triage history — "Added to [group] on [date]" and "Moved from [old] to [new] on [date]"
- [ ] **RTRI-05**: Human integration test validates re-triage workflow end-to-end
- [ ] **RTRI-06**: `add_to_inbox` only adds Inbox label to emails that were in Screener at triage time — re-triage does NOT add Inbox to existing emails (they are not new)

### Milestone Closeout

- [ ] **CLOSE-01**: `docs/WIP.md` finalized into proper documentation and integrated into `docs/` at end of milestone

## Future Requirements

### Observability (v1.3)

- **OBS-01**: Dry-run mode that logs intended actions without making changes
- **OBS-02**: Log-based metrics/counters (triaged senders, swept emails, errors)
- **OBS-03**: Prometheus metrics endpoint
- **OBS-04**: Grafana + Loki deployment for log query UI

### Long-term

- **FUTURE-01**: Sweep workflow — re-label archived emails by contact group membership
- **FUTURE-02**: JMAP Contacts API migration (replace CardDAV when RFC 9610 is supported)
- **FUTURE-03**: Programmatic sieve rule creation (blocked: no Fastmail API)

## Out of Scope

| Feature | Reason |
|---------|--------|
| `add_to_inbox` inheritance through parent chain | Explicit per-category is clearer; only labels propagate through parents |
| Backward compatibility with pre-v1.2 config.yaml | Personal project; clean break preferred over migration shims |
| `@MailroomWarning` on re-triage | Re-triage is a supported operation, not an exception |
| Sweep ALL historical sender emails on re-triage | Only sweep from old destination mailbox — bounded scope |
| Re-label archived emails by group membership | Far-future idea (#5), different from re-triage |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEBT-01 | Phase 10 | Complete |
| DEBT-02 | Phase 10 | Complete |
| DEBT-03 | Phase 10 | Complete |
| DEBT-04 | Phase 10 | Complete |
| DEBT-05 | Phase 10 | Complete |
| CFG-01 | Phase 11 | Complete |
| CFG-02 | Phase 11 | Complete |
| CFG-03 | Phase 11 | Complete |
| CFG-04 | Phase 11 | Complete |
| CFG-05 | Phase 11 | Complete |
| CFG-06 | Phase 11 | Complete |
| CFG-07 | Phase 11 | Complete |
| CFG-08 | Phase 11 | Complete |
| SCAN-01 | Phase 12 | Complete |
| SCAN-02 | Phase 12 | Complete |
| SCAN-03 | Phase 12 | Complete |
| RTRI-01 | Phase 13 | Complete |
| RTRI-02 | Phase 13 | Complete |
| RTRI-03 | Phase 13 | Pending |
| RTRI-04 | Phase 13 | Complete |
| RTRI-05 | Phase 13 | Pending |
| RTRI-06 | Phase 13 | Pending |
| CLOSE-01 | Post-Phase 13 | Pending |

**Coverage:**
- v1.2 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-03-02*
*Last updated: 2026-03-02 after roadmap creation*
