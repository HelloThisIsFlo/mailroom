# Mailroom

## What This Is

A background Python service that replicates HEY Mail's Screener workflow on Fastmail. Users triage unknown senders by applying a label on their phone (`@ToImbox`, `@ToFeed`, `@ToPaperTrail`, `@ToJail`), and Mailroom automatically adds the sender to the right Fastmail contact group, sweeps all their emails out of the Screener, and ensures future emails are routed correctly by existing Fastmail rules. Built for one user migrating from HEY to Fastmail.

## Core Value

One label tap on a phone triages an entire sender — all their backlogged emails move to the right place, and all future emails are auto-routed.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Poll Fastmail for emails with triage labels (`@ToImbox`, `@ToFeed`, `@ToPaperTrail`, `@ToJail`)
- [ ] Extract sender email address from triaged emails
- [ ] Add sender to contacts and assign to correct contact group via CardDAV
- [ ] Handle existing contacts — add to group without creating duplicates
- [ ] Remove triage label from processed email
- [ ] Sweep all Screener emails from same sender to correct destination
- [ ] For Imbox triage: re-add Inbox label to swept emails so they appear immediately
- [ ] Retry on failure — leave triage label in place if CardDAV fails, retry next poll cycle
- [ ] Structured JSON logging (action, sender, timestamp)
- [ ] Containerized with Docker, deployable to Kubernetes
- [ ] ConfigMap-driven configuration (polling interval, label names, contact group names)
- [ ] Secrets managed via Kubernetes Secret (API token, CardDAV password)

### Out of Scope

- `List-Unsubscribe` header auto-classification — future idea, not part of v1
- Pluggable workflow engine / plugin system — v1 is Screener-only, but code will be cleanly separated for future extensibility
- CI/CD pipeline — manual build-and-push is sufficient
- noreply address cleanup — known gotcha, can be addressed later
- Fastmail webhooks — not supported by Fastmail, polling is the only option

## Context

- Migrating from HEY Mail to Fastmail. HEY's Screener was the killer feature; this project brings it to Fastmail.
- Fastmail rules and labels are already configured: unknown senders → `Screener` label; contact group members → their respective labels.
- The UX gap: assigning a contact to a group on iOS Fastmail is tedious (many taps). Applying a label is one tap. This service bridges that gap.
- Fastmail uses JMAP for email operations and CardDAV for contacts (JMAP contacts spec not finalized).
- Jail ≠ Block. Jail is a soft-reject with periodic review (~every 3 weeks). Never use Fastmail's block feature.
- Every screened sender ends up in exactly one of four contact groups (Imbox, Feed, Paper Trail, Jail), making future cleanup possible via group membership.

## Constraints

- **API Protocol**: JMAP for email, CardDAV for contacts — Fastmail does not support JMAP for contacts yet
- **No Webhooks**: Fastmail has no push/webhook support; must poll (every 5 minutes is sufficient)
- **Deployment**: Existing home Kubernetes cluster, manual deploy via `kubectl apply`
- **Language**: Python
- **Architecture**: Clean separation of concerns — Screener logic in its own module, clear interfaces — to support future extensibility without building a plugin system now

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Polling over webhooks | Fastmail doesn't support webhooks | — Pending |
| JMAP + CardDAV (not pure JMAP) | JMAP contacts spec not finalized | — Pending |
| Retry on failure (leave triage label) | Safer than silently dropping; next poll retries | — Pending |
| Re-add Inbox label on Imbox sweep | Swept emails should appear in Inbox immediately, not stay archived | — Pending |
| Structured JSON logs | Running headless on k8s cluster, need queryable logs | — Pending |
| Clean module separation (not plugin system) | Extensibility prep without over-engineering v1 | — Pending |
| ghcr.io for container registry | Free, works with GitHub repos, no extra infra | — Pending |

---
*Last updated: 2026-02-23 after initialization*
