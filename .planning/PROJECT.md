# Mailroom

## What This Is

A background Python service that replicates HEY Mail's Screener workflow on Fastmail. Users triage unknown senders by applying a label on their phone (`@ToImbox`, `@ToFeed`, `@ToPaperTrail`, `@ToJail`, `@ToPerson`), and Mailroom automatically adds the sender to the right Fastmail contact group, sweeps all their emails out of the Screener, and ensures future emails are routed correctly by existing Fastmail rules. Supports both company and person contact types. Built for one user migrating from HEY to Fastmail.

## Core Value

One label tap on a phone triages an entire sender — all their backlogged emails move to the right place, and all future emails are auto-routed.

## Current Milestone: v1.1 Push & Config

**Goal:** Replace polling with push notifications, make triage categories user-configurable, and add automated Fastmail setup.

**Target features:**
- Replace polling with JMAP EventSource push notifications (SSE with debounce, polling fallback)
- Make triage label/group/inbox mappings user-configurable (not hardcoded in config defaults)
- Setup script that provisions required labels and contact groups on Fastmail automatically

## Requirements

### Validated

- ✓ Poll Fastmail for emails with triage labels (`@ToImbox`, `@ToFeed`, `@ToPaperTrail`, `@ToJail`, `@ToPerson`) — v1.0
- ✓ Extract sender email address from triaged emails — v1.0
- ✓ Add sender to contacts and assign to correct contact group via CardDAV — v1.0
- ✓ Handle existing contacts — add to group without creating duplicates — v1.0
- ✓ Remove triage label from processed email — v1.0
- ✓ Sweep all Screener emails from same sender to correct destination — v1.0
- ✓ For Imbox triage: re-add Inbox label to swept emails so they appear immediately — v1.0
- ✓ Retry on failure — leave triage label in place if CardDAV fails, retry next poll cycle — v1.0
- ✓ Structured JSON logging (action, sender, timestamp) — v1.0
- ✓ Containerized with Docker, deployable to Kubernetes — v1.0
- ✓ ConfigMap-driven configuration (polling interval, label names, contact group names) — v1.0
- ✓ Secrets managed via Kubernetes Secret (API token, CardDAV password) — v1.0
- ✓ Person/company contact types via @ToPerson label — v1.0 (bonus)
- ✓ Sender display name preservation when creating contacts — v1.0 (bonus, originally v2)
- ✓ Health/liveness probe for k8s restart on hang — v1.0 (bonus, originally v2)

### Active

- [ ] Replace polling with JMAP EventSource push (SSE listener, debounce, polling fallback)
- [ ] Make triage label/group/inbox mappings user-configurable
- [ ] Setup script that provisions required labels and contact groups on Fastmail

### Future Milestones

**v1.2 Re-triage & Expanded Scanning:**
- Re-triage support — moving a sender from one group to another
- Scan for action labels beyond screener mailbox
- Broader action label support

**v1.3 Observability:**
- Dry-run mode that logs intended actions without making changes
- Log-based metrics/counters (triaged senders, swept emails, errors)
- Prometheus metrics endpoint

### Out of Scope

- AI/ML auto-classification — product philosophy is human-decides, not algorithm
- Webhooks — Fastmail does not support inbound webhooks (EventSource/SSE is used instead for push)
- Web UI / dashboard — single-user tool; Fastmail IS the UI
- Multi-account support — single user; deploy separate instances if needed
- CI/CD pipeline — manual build-and-push is sufficient for a personal tool
- `List-Unsubscribe` header auto-classification — future idea, complexity not justified yet
- Pluggable workflow engine — v1 code is cleanly separated; plugin system is premature
- noreply address cleanup — known gotcha, can be addressed later
- IMAP IDLE — over-engineering; EventSource is the correct JMAP push mechanism

## Context

Shipped v1.0 with 8,666 LOC Python across 122 files.
Tech stack: Python, JMAP (httpx), CardDAV (httpx + vobject), pydantic-settings, structlog, Docker, Kubernetes.
180 unit tests + 13 human integration tests against live Fastmail.
Deployed as a single-replica k8s Deployment polling every 5 minutes.
Phase 3.1 was an inserted phase adding person/company contact type support beyond original scope.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Polling over webhooks | Fastmail doesn't support webhooks | ✓ Good — 5-min poll is fast enough for triage UX |
| JMAP + CardDAV (not pure JMAP) | JMAP contacts spec not finalized | ✓ Good — CardDAV proven reliable against live Fastmail |
| Retry on failure (leave triage label) | Safer than silently dropping; next poll retries | ✓ Good — zero lost triages in testing |
| Re-add Inbox label on Imbox sweep | Swept emails should appear in Inbox immediately | ✓ Good — emails appear immediately after triage |
| Structured JSON logs | Running headless on k8s, need queryable logs | ✓ Good — structlog JSON mode works well |
| Clean module separation (not plugin system) | Extensibility prep without over-engineering v1 | ✓ Good — JMAPClient, CardDAVClient, ScreenerWorkflow are clean boundaries |
| ghcr.io for container registry | Free, works with GitHub repos, no extra infra | ✓ Good — GitHub Actions CI pushes automatically |
| CardDAV as validation gate (Phase 2) | KIND:group model from training data, unverified | ✓ Good — live validation prevented building on assumptions |
| Company-default contacts with @ToPerson override | Most senders are companies; person-type is opt-in | ✓ Good — clean separation, users choose explicitly |
| Batch chunking at 100 emails per JMAP call | Conservative under 500 minimum maxObjectsInSet | ✓ Good — no batch size errors observed |
| Individual env vars (not structured config) | Maps cleanly to k8s ConfigMap entries | ✓ Good — envFrom injects all 18 vars directly |

## Constraints

- **API Protocol**: JMAP for email, CardDAV for contacts — Fastmail does not support JMAP for contacts yet
- **No Webhooks**: Fastmail has no inbound webhook support; push via JMAP EventSource (SSE) with polling fallback
- **Deployment**: Existing home Kubernetes cluster, manual deploy via `kubectl apply`
- **Language**: Python
- **Architecture**: Clean separation of concerns — Screener logic in its own module, clear interfaces

---
*Last updated: 2026-02-25 after v1.1 milestone start*
