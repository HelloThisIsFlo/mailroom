# Requirements: Mailroom

**Defined:** 2026-02-25
**Core Value:** One label tap on a phone triages an entire sender — all their backlogged emails move to the right place, and all future emails are auto-routed.

## v1.1 Requirements

Requirements for v1.1 Push & Config milestone. Each maps to roadmap phases.

### Configurable Categories

- [x] **CONFIG-01**: Triage categories defined as a structured list (label, contact group, destination mailbox, add-inbox flag per category)
- [x] **CONFIG-02**: Categories configurable via `MAILROOM_TRIAGE_CATEGORIES` JSON environment variable
- [x] **CONFIG-03**: Default categories match v1.0 behavior (Imbox, Feed, PaperTrail, Jail, Person) so zero-config deployments work
- [x] **CONFIG-04**: All derived properties (triage labels, contact groups, required mailboxes) computed from category mapping
- [x] **CONFIG-05**: User can add custom triage categories beyond the 5 defaults
- [x] **CONFIG-06**: Startup validation rejects invalid category configurations (missing fields, duplicate labels)

### Setup Script

- [x] **SETUP-01**: Setup script creates missing triage label mailboxes on Fastmail via JMAP `Mailbox/set`
- [x] **SETUP-02**: Setup script creates missing contact groups on Fastmail via CardDAV
- [x] **SETUP-03**: Setup script is idempotent — reports "already exists" for items that are already present
- [x] **SETUP-04**: Setup script outputs human-readable sieve rule instructions for email routing (cannot be automated)
- [x] **SETUP-05**: Setup script requires `--apply` flag to make changes (dry-run by default)
- [x] **SETUP-06**: Setup script reads categories from the same config as the main service

### EventSource Push

- [x] **PUSH-01**: SSE listener connects to Fastmail EventSource endpoint with Bearer auth
- [x] **PUSH-02**: State change events trigger triage pass with configurable debounce window (default 3s)
- [x] **PUSH-03**: Liveness detection via ping-based timeout (read timeout > 2x ping interval)
- [x] **PUSH-04**: Auto-reconnect with exponential backoff on disconnect (1s -> 2s -> 4s -> max 60s)
- [x] **PUSH-05**: Health endpoint reports EventSource connection status and thread liveness
- [x] **PUSH-06**: Triage latency reduced from up to 5 minutes to under 10 seconds for push-triggered events

## Future Requirements

### v1.2 Re-triage & Expanded Scanning

- **RETRI-01**: User can move a sender from one contact group to another (re-triage)
- **RETRI-02**: Service scans for action labels beyond screener mailbox
- **RETRI-03**: Broader action label support across mailboxes

### v1.3 Observability

- **OBS-01**: Dry-run mode that logs intended actions without making changes
- **OBS-02**: Log-based metrics/counters (triaged senders, swept emails, errors)
- **OBS-03**: Prometheus metrics endpoint

## Out of Scope

| Feature | Reason |
|---------|--------|
| Backward compatibility with v1.0 flat env vars | Clean break — v1.0 just shipped, no established user base |
| Sieve rule creation via API | Fastmail has no API for filter rules; setup script outputs human instructions instead |
| Nested mailbox hierarchy | Flat namespace only in v1.1; defer to v1.2 if needed |
| Per-event-type processing | Premature optimization; `workflow.poll()` is fast and idempotent |
| YAML/TOML config file | JSON env var sufficient for k8s ConfigMap; file-based config is v1.2+ |
| Async runtime (asyncio) | Synchronous-by-design; single-user service gains nothing from async |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONFIG-01 | Phase 6 | Complete |
| CONFIG-02 | Phase 6 | Complete |
| CONFIG-03 | Phase 6 | Complete |
| CONFIG-04 | Phase 6 | Complete |
| CONFIG-05 | Phase 6 | Complete |
| CONFIG-06 | Phase 6 | Complete |
| SETUP-01 | Phase 7 | Complete |
| SETUP-02 | Phase 7 | Complete |
| SETUP-03 | Phase 7 | Complete |
| SETUP-04 | Phase 7 | Complete |
| SETUP-05 | Phase 7 | Complete |
| SETUP-06 | Phase 7 | Complete |
| PUSH-01 | Phase 8 | Complete |
| PUSH-02 | Phase 8 | Complete |
| PUSH-03 | Phase 8 | Complete |
| PUSH-04 | Phase 8 | Complete |
| PUSH-05 | Phase 8 | Complete |
| PUSH-06 | Phase 8 | Complete |

**Coverage:**
- v1.1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-02-25*
*Last updated: 2026-02-25 after roadmap creation*
