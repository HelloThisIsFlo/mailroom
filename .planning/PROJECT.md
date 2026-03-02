# Mailroom

## What This Is

A background Python service that replicates HEY Mail's Screener workflow on Fastmail. Users triage unknown senders by applying a label on their phone (`@ToImbox`, `@ToFeed`, `@ToPaperTrail`, `@ToJail`, `@ToPerson`), and Mailroom automatically adds the sender to the right Fastmail contact group, sweeps all their emails out of the Screener, and ensures future emails are routed correctly by existing Fastmail rules. Supports both company and person contact types. Triage categories are fully configurable via YAML, with an idempotent setup CLI that provisions Fastmail resources. Push notifications via JMAP EventSource deliver sub-10-second triage latency with polling fallback. Deployed as a Helm chart on Kubernetes. Built for one user migrating from HEY to Fastmail.

## Core Value

One label tap on a phone triages an entire sender — all their backlogged emails move to the right place, and all future emails are auto-routed.

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
- ✓ Triage categories configurable via structured YAML config with zero-config defaults — v1.1
- ✓ All derived properties (labels, groups, mailboxes) computed from category mapping — v1.1
- ✓ Startup validation rejects invalid category configurations — v1.1
- ✓ Setup script provisions mailboxes and contact groups on Fastmail with dry-run safety — v1.1
- ✓ Setup script outputs sieve rule guidance for manual email routing configuration — v1.1
- ✓ JMAP EventSource push with sub-10-second triage latency — v1.1
- ✓ Auto-reconnect with exponential backoff on SSE disconnect — v1.1
- ✓ Polling fallback when SSE unavailable — v1.1
- ✓ Health endpoint reports EventSource status and thread liveness — v1.1
- ✓ Config.yaml replaces env vars for non-secret settings — v1.1 (inserted)
- ✓ Helm chart deployment with secrets-values.yaml pattern — v1.1 (inserted)

### Active

(None — next milestone requirements defined via `/gsd:new-milestone`)

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
- Async runtime (asyncio) — synchronous-by-design; single-user service gains nothing from async
- Backward compatibility with v1.0 flat env vars — clean break, no established user base
- Sieve rule creation via API — Fastmail has no API for filter rules
- Nested mailbox hierarchy — flat namespace sufficient

## Context

Shipped v1.1 with 12,572 LOC Python across 46 files.
Tech stack: Python, JMAP (httpx), CardDAV (httpx + vobject), pydantic-settings + YAML, structlog, Click CLI, Docker, Helm/Kubernetes.
278 unit tests + 16 human integration tests against live Fastmail.
Deployed as a Helm chart on home Kubernetes cluster with JMAP EventSource push (sub-10s triage).
Two inserted phases (9.1 config.yaml, 9.1.1 Helm chart) added during milestone for deployment improvements.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Polling over webhooks | Fastmail doesn't support webhooks | ✓ Good — replaced by EventSource push in v1.1, polling kept as fallback |
| JMAP + CardDAV (not pure JMAP) | JMAP contacts spec not finalized | ✓ Good — CardDAV proven reliable against live Fastmail |
| Retry on failure (leave triage label) | Safer than silently dropping; next poll retries | ✓ Good — zero lost triages in testing |
| Re-add Inbox label on Imbox sweep | Swept emails should appear in Inbox immediately | ✓ Good — emails appear immediately after triage |
| Structured JSON logs | Running headless on k8s, need queryable logs | ✓ Good — structlog JSON mode works well |
| Clean module separation (not plugin system) | Extensibility prep without over-engineering v1 | ✓ Good — JMAPClient, CardDAVClient, ScreenerWorkflow are clean boundaries |
| ghcr.io for container registry | Free, works with GitHub repos, no extra infra | ✓ Good — GitHub Actions CI pushes automatically |
| CardDAV as validation gate (Phase 2) | KIND:group model from training data, unverified | ✓ Good — live validation prevented building on assumptions |
| Company-default contacts with @ToPerson override | Most senders are companies; person-type is opt-in | ✓ Good — clean separation, users choose explicitly |
| Batch chunking at 100 emails per JMAP call | Conservative under 500 minimum maxObjectsInSet | ✓ Good — no batch size errors observed |
| Two-pass category resolution | Handle any parent/child declaration order | ✓ Good — no ordering constraints on user config |
| Guidance-only sieve module | No Fastmail API for filter rules | ✓ Good — outputs instructions for all categories |
| SSE via httpx streaming | Consistency with existing JMAP client | ✓ Good — shared session, single HTTP library |
| Drain-wait-drain debounce pattern | Collapse rapid SSE events into one poll | ✓ Good — prevents thundering herd on state changes |
| Queue sentinel for shutdown | `put(None)` in signal handler for instant wakeup | ✓ Good — graceful shutdown < 1s |
| Config.yaml over env vars | Nested config, name-only shorthand, cleaner K8s | ✓ Good — auth stays as env vars for secrets |
| Helm chart over plain manifests | Templated values, secrets-values.yaml pattern | ✓ Good — simplified deployment and config management |

## Constraints

- **API Protocol**: JMAP for email, CardDAV for contacts — Fastmail does not support JMAP for contacts yet
- **No Webhooks**: Fastmail has no inbound webhook support; push via JMAP EventSource (SSE) with polling fallback
- **Deployment**: Home Kubernetes cluster, Helm chart deploy via `helm upgrade --install`
- **Language**: Python
- **Architecture**: Clean separation of concerns — Screener logic in its own module, clear interfaces

---
*Last updated: 2026-03-02 after v1.1 milestone*
