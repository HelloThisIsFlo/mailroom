# Mailroom

## What This Is

A background Python service that replicates HEY Mail's Screener workflow on Fastmail. Users triage unknown senders by applying a label on their phone, and Mailroom automatically adds the sender to the right Fastmail contact group, sweeps all their emails to the correct destination, and ensures future emails are auto-routed by existing Fastmail sieve rules. Supports parent-child category hierarchies with additive label propagation, re-triage for moving senders between groups, contact provenance tracking for clean reset, and batched label scanning beyond the Screener mailbox. Categories are fully configurable via YAML, with an idempotent setup CLI and a provenance-aware reset CLI. Push notifications via JMAP EventSource deliver sub-10-second triage latency with polling fallback. Deployed as a Helm chart on Kubernetes. Built for one user migrating from HEY to Fastmail.

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
- ✓ Sender display name preservation when creating contacts — v1.0 (bonus)
- ✓ Health/liveness probe for k8s restart on hang — v1.0 (bonus)
- ✓ Triage categories configurable via structured YAML config with zero-config defaults — v1.1
- ✓ All derived properties (labels, groups, mailboxes) computed from category mapping — v1.1
- ✓ Startup validation rejects invalid category configurations — v1.1
- ✓ Setup script provisions mailboxes and contact groups on Fastmail with dry-run safety — v1.1
- ✓ Setup script outputs sieve rule guidance for manual email routing configuration — v1.1
- ✓ JMAP EventSource push with sub-10-second triage latency — v1.1
- ✓ Auto-reconnect with exponential backoff on SSE disconnect — v1.1
- ✓ Polling fallback when SSE unavailable — v1.1
- ✓ Health endpoint reports EventSource status and thread liveness — v1.1
- ✓ Config.yaml replaces env vars for non-secret settings — v1.1
- ✓ Helm chart deployment with secrets-values.yaml pattern — v1.1
- ✓ Independent `add_to_inbox` flag per category (does not inherit through parent chain) — v1.2
- ✓ `destination_mailbox: Inbox` rejected with clear error pointing to `add_to_inbox` — v1.2
- ✓ Child categories resolve as fully independent (own label, contact group, destination mailbox) — v1.2
- ✓ Parent relationship applies additive label chain (not field inheritance) — v1.2
- ✓ Circular parent references detected and rejected at startup — v1.2
- ✓ Triage labels discovered via batched label mailbox queries (not limited to Screener) — v1.2
- ✓ All label mailbox queries in single JMAP HTTP round-trip — v1.2
- ✓ Per-method errors in batched JMAP responses detected and handled — v1.2
- ✓ Re-triage moves sender to new contact group with email re-filing — v1.2
- ✓ Contact note captures triage history with dates — v1.2
- ✓ Re-triage logged as `group_reassigned` structured event — v1.2
- ✓ `add_to_inbox` only adds Inbox at initial triage from Screener (not on re-triage) — v1.2
- ✓ Config `mailroom:` section with provenance_group, label_error, label_warning — v1.2
- ✓ Provenance contact group tracks created vs. adopted contacts — v1.2
- ✓ `@MailroomWarning` cleaned on every successful triage, reapplied if condition persists — v1.2
- ✓ Provenance-aware reset: delete created, warn modified, strip adopted contacts — v1.2
- ✓ Reset follows 7-step operation order with confirmation prompt — v1.2
- ✓ Human integration test validates re-triage workflow end-to-end — v1.2

### Active

(None — planning next milestone)

### Future Milestones

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
- Pluggable workflow engine — code is cleanly separated; plugin system is premature
- noreply address cleanup — known gotcha, can be addressed later
- Async runtime (asyncio) — synchronous-by-design; single-user service gains nothing from async
- Backward compatibility with pre-v1.2 config formats — clean break, no established user base
- Sieve rule creation via API — Fastmail has no API for filter rules
- `add_to_inbox` inheritance through parent chain — explicit per-category is clearer
- Retroactive provenance migration — provenance tracking starts from v1.2 forward

## Context

Shipped v1.2 with 15,765 LOC Python.
Tech stack: Python, JMAP (httpx), CardDAV (httpx + vobject), pydantic-settings + YAML, structlog, Click CLI, Docker, Helm/Kubernetes.
407 unit tests + 18 human integration tests against live Fastmail.
Deployed as a Helm chart on home Kubernetes cluster with JMAP EventSource push (sub-10s triage).
v1.2 added parent-child category hierarchies, batched label scanning, re-triage with group reassignment, contact provenance tracking, and provenance-aware reset.
Documentation finalized: workflow.md, config.md, architecture.md with mermaid diagrams.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Polling over webhooks | Fastmail doesn't support webhooks | ✓ Good — replaced by EventSource push in v1.1, polling kept as fallback |
| JMAP + CardDAV (not pure JMAP) | JMAP contacts spec not finalized | ✓ Good — CardDAV proven reliable against live Fastmail |
| Retry on failure (leave triage label) | Safer than silently dropping; next poll retries | ✓ Good — zero lost triages in testing |
| Re-add Inbox label on Imbox sweep | Swept emails should appear in Inbox immediately | ✓ Good — emails appear immediately after triage |
| Structured JSON logs | Running headless on k8s, need queryable logs | ✓ Good — structlog JSON mode works well |
| Clean module separation (not plugin system) | Extensibility prep without over-engineering | ✓ Good — JMAPClient, CardDAVClient, ScreenerWorkflow are clean boundaries |
| ghcr.io for container registry | Free, works with GitHub repos, no extra infra | ✓ Good — GitHub Actions CI pushes automatically |
| Company-default contacts with @ToPerson override | Most senders are companies; person-type is opt-in | ✓ Good — clean separation, users choose explicitly |
| Batch chunking at 100 emails per JMAP call | Conservative under 500 minimum maxObjectsInSet | ✓ Good — no batch size errors observed |
| Two-pass category resolution | Handle any parent/child declaration order | ✓ Good — no ordering constraints on user config |
| Guidance-only sieve module | No Fastmail API for filter rules | ✓ Good — outputs instructions for all categories |
| SSE via httpx streaming | Consistency with existing JMAP client | ✓ Good — shared session, single HTTP library |
| Drain-wait-drain debounce pattern | Collapse rapid SSE events into one poll | ✓ Good — prevents thundering herd on state changes |
| Config.yaml over env vars | Nested config, name-only shorthand, cleaner K8s | ✓ Good — auth stays as env vars for secrets |
| Helm chart over plain manifests | Templated values, secrets-values.yaml pattern | ✓ Good — simplified deployment and config management |
| Additive parent labels (not field inheritance) | Children are independent categories; parent adds labels only | ✓ Good — clean model, no confusing overrides — v1.2 |
| `add_to_inbox` explicit per-category | Inheritance would be confusing; only labels propagate | ✓ Good — clear intent per category — v1.2 |
| Batched JMAP queries for label scanning | Single HTTP round-trip for all label mailboxes | ✓ Good — efficient scanning regardless of category count — v1.2 |
| Add-to-new-first group reassignment | Safe partial-failure order for contact group moves | ✓ Good — sender never orphaned from all groups — v1.2 |
| Provenance group as infrastructure | Invisible to triage pipeline, excluded from check_membership | ✓ Good — clean separation of concerns — v1.2 |
| 7-step reset operation order | Deterministic, testable, documented ordering | ✓ Good — each step has clear pre/post conditions — v1.2 |
| `labels:` → `mailroom:` config rename | Broader scope than just labels (provenance, warnings) | ✓ Good — no backward compat needed for personal tool — v1.2 |

## Constraints

- **API Protocol**: JMAP for email, CardDAV for contacts — Fastmail does not support JMAP for contacts yet
- **No Webhooks**: Fastmail has no inbound webhook support; push via JMAP EventSource (SSE) with polling fallback
- **Deployment**: Home Kubernetes cluster, Helm chart deploy via `helm upgrade --install`
- **Language**: Python
- **Architecture**: Clean separation of concerns — Screener logic in its own module, clear interfaces

---
*Last updated: 2026-03-05 after v1.2 milestone*
