# Requirements: Mailroom

**Defined:** 2026-02-23
**Core Value:** One label tap on a phone triages an entire sender — all their backlogged emails move to the right place, and all future emails are auto-routed.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### JMAP Integration

- [ ] **JMAP-01**: Service can authenticate with Fastmail JMAP API using Bearer token
- [ ] **JMAP-02**: Service can resolve mailbox names to mailbox IDs (Screener, @ToImbox, @ToFeed, @ToPaperTrail, @ToJail, Inbox)
- [ ] **JMAP-03**: Service can query emails by mailbox/label to find triaged emails
- [ ] **JMAP-04**: Service can extract sender email address from a triaged email
- [ ] **JMAP-05**: Service can remove a triage label from a processed email using JMAP patch syntax
- [ ] **JMAP-06**: Service can query Screener for all emails from a specific sender
- [ ] **JMAP-07**: Service can batch-update swept emails (remove Screener label, add destination label)
- [ ] **JMAP-08**: Service can add Inbox label to swept emails when destination is Imbox

### CardDAV Integration

- [ ] **CDAV-01**: Service can authenticate with Fastmail CardDAV using Basic auth (app password)
- [ ] **CDAV-02**: Service can search contacts by email address to check for existing contacts
- [ ] **CDAV-03**: Service can create a new contact vCard for a sender
- [ ] **CDAV-04**: Service can add a contact to a contact group (Imbox, Feed, Paper Trail, Jail)
- [ ] **CDAV-05**: Service handles existing contacts — adds to group without creating duplicates

### Triage Workflow

- [ ] **TRIAGE-01**: Service polls for emails with triage labels every 5 minutes (configurable)
- [ ] **TRIAGE-02**: For each triaged email: extract sender, create/update contact, assign to group, remove triage label
- [ ] **TRIAGE-03**: After contact assignment, sweep all Screener emails from that sender to the correct destination
- [ ] **TRIAGE-04**: For Imbox triage: swept emails get Inbox label re-added so they appear immediately
- [ ] **TRIAGE-05**: Processing is idempotent — re-processing the same email does not create duplicate contacts
- [ ] **TRIAGE-06**: If CardDAV fails, triage label is left in place for retry on next poll cycle

### Logging & Configuration

- [ ] **CONF-01**: All label names and contact group names are configurable via environment variables (k8s ConfigMap)
- [ ] **CONF-02**: Polling interval is configurable via environment variable
- [ ] **CONF-03**: Fastmail credentials are read from environment variables (k8s Secret)
- [ ] **LOG-01**: Service produces structured JSON logs with action, sender, timestamp, success/failure
- [ ] **LOG-02**: Errors are logged with enough context to diagnose without accessing the cluster

### Deployment

- [ ] **DEPLOY-01**: Dockerfile builds a slim Python image with all dependencies
- [ ] **DEPLOY-02**: k8s Deployment manifest with 1 replica and resource limits
- [ ] **DEPLOY-03**: k8s Secret manifest template for Fastmail credentials (actual values not committed)
- [ ] **DEPLOY-04**: k8s ConfigMap manifest with all configurable values
- [ ] **DEPLOY-05**: Image is pushed to ghcr.io and deployable via `kubectl apply -f k8s/`

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enhanced Triage

- **TRIAGE-10**: Re-triage support — moving a sender from one group to another (remove from old, add to new)
- **TRIAGE-11**: Sender display name preservation when creating contacts

### Operational

- **OPS-01**: Dry-run mode that logs intended actions without making changes
- **OPS-02**: Health/liveness probe for k8s restart on hang
- **OPS-03**: Log-based metrics/counters (triaged senders, swept emails, errors)

### Future

- **FUTURE-01**: List-Unsubscribe header auto-classification for newsletters
- **FUTURE-02**: Pluggable workflow engine for other Fastmail automations
- **FUTURE-03**: noreply address detection/cleanup during triage

## Out of Scope

| Feature | Reason |
|---------|--------|
| AI/ML auto-classification | Product philosophy is human-decides, not algorithm. Defeats the Screener model. |
| Webhook/push triggers | Fastmail does not support webhooks. Polling is the only option. |
| Web UI / dashboard | Single-user tool. Fastmail IS the UI. |
| Multi-account support | Single user. Deploy separate instances if needed. |
| Auto-unsubscribe for Jailed senders | List-Unsubscribe is unreliable. Jail is soft-reject, not permanent. |
| CI/CD pipeline | Manual build-and-push is sufficient for a personal tool. |
| Real-time notifications | User initiated the triage — they know it happened. |
| IMAP IDLE | Over-engineering. 5-minute polling is fast enough for triage. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| JMAP-01 | — | Pending |
| JMAP-02 | — | Pending |
| JMAP-03 | — | Pending |
| JMAP-04 | — | Pending |
| JMAP-05 | — | Pending |
| JMAP-06 | — | Pending |
| JMAP-07 | — | Pending |
| JMAP-08 | — | Pending |
| CDAV-01 | — | Pending |
| CDAV-02 | — | Pending |
| CDAV-03 | — | Pending |
| CDAV-04 | — | Pending |
| CDAV-05 | — | Pending |
| TRIAGE-01 | — | Pending |
| TRIAGE-02 | — | Pending |
| TRIAGE-03 | — | Pending |
| TRIAGE-04 | — | Pending |
| TRIAGE-05 | — | Pending |
| TRIAGE-06 | — | Pending |
| CONF-01 | — | Pending |
| CONF-02 | — | Pending |
| CONF-03 | — | Pending |
| LOG-01 | — | Pending |
| LOG-02 | — | Pending |
| DEPLOY-01 | — | Pending |
| DEPLOY-02 | — | Pending |
| DEPLOY-03 | — | Pending |
| DEPLOY-04 | — | Pending |
| DEPLOY-05 | — | Pending |

**Coverage:**
- v1 requirements: 29 total
- Mapped to phases: 0
- Unmapped: 29 ⚠️

---
*Requirements defined: 2026-02-23*
*Last updated: 2026-02-23 after initial definition*
