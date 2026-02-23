# Project Research Summary

**Project:** Mailroom (Fastmail Email Triage Automation)
**Domain:** Polling-based email automation service (JMAP + CardDAV)
**Researched:** 2026-02-23
**Confidence:** MEDIUM-HIGH

## Executive Summary

Mailroom is a headless background service that replicates HEY Mail's Screener workflow on Fastmail. The service polls for emails marked with triage labels (@ToImbox, @ToFeed, @ToPaperTrail, @ToJail), extracts the sender, adds them to a Fastmail contact group (which triggers Fastmail's native email routing rules), sweeps all matching Screener emails to the correct destination, and removes the triage label. The architecture is intentionally minimal: a synchronous Python polling loop with no database, no web framework, no async, and no AI. The human triages; the service executes. The tool deploys as a single pod to a home Kubernetes cluster.

The recommended stack is well-defined and high-confidence. Python 3.13 with uv, `jmapc` for JMAP email operations, raw `requests` + `vobject` + `lxml` for CardDAV contact management, `pydantic-settings` for configuration, `structlog` for JSON logging, and `tenacity` for retry. The main library risk is `jmapc` (v0.2.x, single maintainer, GPL-3.0) — but JMAP is simple enough that a thin replacement using raw requests is feasible if needed. CardDAV has no suitable Python library, so a bespoke ~200-line client module is required; this is well-understood and manageable.

The biggest risks are all in CardDAV integration: using the wrong contact group model (CATEGORIES vs. KIND:group), forgetting ETag concurrency handling, and producing vCard format mismatches. These are not complex to solve once understood, but they are silent — wrong code looks like it works until Fastmail rules silently fail to route email. The Phase 2 CardDAV work must include live Fastmail validation before the full triage pipeline is built on top of it.

## Key Findings

### Recommended Stack

The stack is deliberately thin for a single-task polling service. `jmapc` is the only maintained Python JMAP client and covers every operation Mailroom needs. CardDAV has no suitable library, so the implementation uses raw HTTP with `requests`, XML parsing with `lxml`, and vCard handling with `vobject`. All other choices (uv, ruff, structlog, pydantic-settings, tenacity) are the current Python ecosystem standards with high confidence.

**Core technologies:**
- **Python 3.13 + uv**: Runtime and package management — fastest toolchain, lockfile support, single tool replacing pip/venv/poetry
- **jmapc 0.2.23**: JMAP email operations — only maintained Python JMAP client; covers Email/query, Email/get, Email/set, Mailbox ops; GPL-3.0; single-maintainer risk acceptable for a personal service
- **requests + vobject + lxml**: CardDAV contact management — no library exists; raw HTTP is the standard approach; well-documented RFC
- **pydantic-settings**: Configuration from env vars — type validation at startup, ConfigMap-friendly, fail-fast on missing config
- **structlog**: Structured JSON logging — processor pipeline, ConsoleRenderer for dev / JSONRenderer for k8s
- **tenacity**: Retry with exponential backoff — declarative decorator pattern, separates retry logic from business logic
- **pytest + responses**: Testing — standard framework; `responses` library mocks HTTP calls from both jmapc and CardDAV code

**What NOT to use:** asyncio (jmapc is sync; no concurrent I/O pressure), web frameworks (background worker, no endpoints), SQLite/PostgreSQL (stateless by design — state lives in Fastmail), APScheduler (a `while True: poll(); sleep(300)` loop is sufficient).

Full details: `.planning/research/STACK.md`

### Expected Features

The product philosophy is explicit: no AI, no magic. Human decides via label, service executes. This distinction positions Mailroom against HEY Mail (Fastmail-specific replica) rather than SaneBox (AI-driven). The feature set is tight.

**Must have (table stakes) — v1:**
- JMAP polling loop — detects triage labels every 5 minutes; the entire system trigger
- Sender extraction — `From` header parsed from JMAP Email/get
- CardDAV contact create/update — idempotent upsert with duplicate prevention (search before create)
- Contact group assignment — adds sender to correct routing group (KIND:group model)
- Triage label removal — acknowledgment that processing succeeded; retry mechanism if skipped
- Screener sweep — moves all emails from triaged sender to destination mailbox
- Inbox re-labeling for Imbox — swept emails must appear in Inbox immediately
- Retry on failure — leave triage label in place on error; next poll cycle retries
- Structured JSON logging — k8s observability for a headless service
- ConfigMap-driven configuration — label names, group names, polling interval are configurable
- Docker + k8s manifests — deployable artifact

**Should have — v1.x (add after core loop is stable):**
- Dry-run mode — log intended actions without executing; invaluable for initial setup
- Health/liveness probe — k8s pod restart on hang
- Re-triage support (group transfer) — move sender between groups; requires removing from old group
- Sender display name preservation — extract display name from `From` header for clean contacts

**Defer to v2+:**
- List-Unsubscribe auto-classification — auto-route newsletters without triage
- Pluggable workflow engine — generalize trigger-action pattern for other Fastmail automations
- noreply address detection — skip or flag noreply senders; heuristic-based, risk of false positives
- Web UI / dashboard — Fastmail's UI is the dashboard; building a separate one is a separate product

Full details: `.planning/research/FEATURES.md`

### Architecture Approach

The architecture is a single synchronous polling loop in one Kubernetes pod. The project structure uses a `src/` layout with two sub-packages: `clients/` (protocol adapters for JMAP and CardDAV) and `workflows/` (business logic that orchestrates client calls). The clients expose domain operations (`find_emails_in_mailbox`, `ensure_contact_in_group`) rather than protocol operations — the rest of the codebase never calls `requests` or `jmapc` directly. The workflow is the "script" that says what happens in what order; the clients say how.

**Major components:**
1. **Main loop (Poller)** — `main.py`; `while True: poll(); sleep(interval)` with signal handling and error recovery
2. **JMAP Client** — `clients/jmap.py`; thin wrapper over `jmapc`; handles mailbox ID resolution, email query/move/label ops
3. **CardDAV Client** — `clients/carddav.py`; raw `requests` + `vobject`; contact search, create, group membership
4. **Screener Workflow** — `workflows/screener.py`; orchestrates triage sequence for each sender; calls both clients
5. **Config + Logging** — `config.py` (pydantic-settings) and `logging.py` (structlog); loaded first, used everywhere

**Key patterns:**
- Thin client wrappers as the core architectural boundary
- Workflow as orchestrator (no protocol logic in business layer)
- Fail-open with retry on next poll (leave triage label in place on error)
- JMAP session created once at startup; session lifecycle managed internally by jmapc
- Mailbox name-to-ID resolution at startup (refresh each poll cycle for safety)

Full details: `.planning/research/ARCHITECTURE.md`

### Critical Pitfalls

Seven critical pitfalls identified. Ordered by severity and phase relevance:

1. **Contact group model confusion (KIND:group vs CATEGORIES)** — Fastmail groups use `KIND:group` vCard with `MEMBER:urn:uuid:<contact-uid>` entries, NOT `CATEGORIES` on individual contacts. Using CATEGORIES produces silent failure: code reports success but Fastmail rules never trigger. Must prototype and verify against live Fastmail before building the triage pipeline. Phase 2.

2. **CardDAV ETag concurrency** — Always send `If-Match: "<etag>"` on PUT. Without it, contact edits (phone numbers, notes) made by the user between GET and PUT are silently overwritten. Handle 412 responses with a bounded retry (3 attempts). Phase 2.

3. **JMAP Mailbox ID vs label name** — Fastmail labels are JMAP Mailboxes with opaque IDs. Never hardcode IDs. Resolve names to IDs via `Mailbox/get` at startup; store names in ConfigMap. Phase 1.

4. **Duplicate contact creation** — CardDAV has no native "find by email" guarantee. Build an in-memory email-to-UID index from a full address book fetch at startup. Normalize email to lowercase before comparison. Refresh on contact creation. Phase 2.

5. **JMAP Email/set patch syntax** — Use patch syntax (`"mailboxIds/<id>": true` to add, `"mailboxIds/<id>": null` to remove) rather than sending the full `mailboxIds` object. Sending the full object accidentally removes the email from all other mailboxes. Phase 1.

6. **JMAP query pagination** — Always check `hasMoreResults` and fetch subsequent pages. Missing pagination silently skips emails when triage backlog exceeds one page. Phase 1.

7. **vCard 3.0/4.0 format mismatch** — Fastmail stores contacts in vCard 3.0. Explicitly set `VERSION:3.0` on new contacts. Verify created contacts display correctly in Fastmail web UI and iOS app. Phase 2.

**Integration gotchas that often bite:**
- JMAP uses Bearer token auth; CardDAV uses Basic auth with a *separate* app password — two credentials, two auth mechanisms
- Trailing slash matters in the CardDAV URL (`/Default/`, not `/Default`)
- Triage label removal must happen AFTER contact group update and email sweep succeed — ordering is critical

Full details: `.planning/research/PITFALLS.md`

## Implications for Roadmap

The architecture research provides an explicit build order: Config/Logging first, then JMAP and CardDAV clients independently, then the Screener Workflow, then the Main Loop, then deployment. This maps naturally to phases. The critical constraint is that CardDAV must be validated against live Fastmail before the triage pipeline is built on top of it — Phase 2 is a validation gate, not just a build step.

### Phase 1: Foundation — Config, Logging, JMAP Client

**Rationale:** Everything depends on configuration being loaded and mailbox IDs being resolved. JMAP is the simpler protocol (library handles session management), so it is the right place to start building confidence. No CardDAV complexity yet.

**Delivers:** A working JMAP client that can query mailboxes, find emails by mailbox, extract senders, move emails, and remove labels. A structured logging setup. A validated configuration model.

**Addresses:** JMAP polling loop (infrastructure), sender extraction, mailbox configuration, structured logging.

**Avoids:** JMAP Mailbox ID hardcoding (resolve by name from startup), JMAP Email/set patch syntax (tested here), missing pagination (implemented here), session URL hardcoding (jmapc handles this, but verified).

**Research flag:** Skip — well-documented library with inspected source code, standard patterns.

### Phase 2: CardDAV Integration (Validation Gate)

**Rationale:** CardDAV is the highest-risk component. The contact group model must be validated against live Fastmail before the triage pipeline is built. This phase must not be rushed. Failures here (wrong group model, vCard format issues) would require rewrites of everything built on top in Phase 3.

**Delivers:** A verified CardDAV client that can search contacts by email, create contacts with correct vCard 3.0 format, and manage group membership using the KIND:group model. Validated against live Fastmail including visual verification in the web UI and iOS app.

**Implements:** `clients/carddav.py`, in-memory contact index for dedup, ETag handling, 412 retry loop.

**Avoids:** Contact group model confusion (verified live), ETag concurrency violations (built in from the start), duplicate contacts (in-memory index), vCard format mismatch (explicit VERSION:3.0, live verification), wrong auth mechanism (separate Basic auth credentials).

**Research flag:** NEEDS deeper research/validation during Phase 2. The KIND:group mechanism is identified but not live-verified. Test against Fastmail before proceeding to Phase 3. Specifically: create a contact group vCard via PUT, add a MEMBER entry, verify the contact appears in the group in the Fastmail web UI, and verify a Fastmail rule targeting that group fires correctly.

### Phase 3: Triage Pipeline (Core Business Logic)

**Rationale:** With validated JMAP and CardDAV clients, the Screener workflow can be assembled. This is where the clients are wired together into the actual triage sequence. The processing order matters: contact upsert first, then Screener sweep, then Inbox re-labeling (for Imbox), then triage label removal. Removing the label last ensures retry safety.

**Delivers:** End-to-end triage: poll, find triage-labeled emails, group by sender, upsert contact into group, sweep Screener emails to destination, re-label for Imbox, remove triage label. Handles re-triage (group transfer) and multiple triage labels on one email.

**Implements:** `workflows/screener.py`, grouped-by-sender processing, sweep with Inbox re-label, re-triage logic (remove from old group, add to new group).

**Avoids:** Polling loop drift (sender-grouped processing, pagination already in Phase 1), triage label removal ordering (last step), multiple triage labels on one email (graceful handling), re-triage without group removal (explicit removal logic).

**Research flag:** Skip — patterns are well-defined from architecture and pitfalls research. Implementation is primarily about correctly assembling Phase 1 and Phase 2 components.

### Phase 4: Main Loop, Observability, and Hardening

**Rationale:** The poller shell (signal handling, error recovery, sleep interval) is the simplest component but must be robust. Observability and hardening features (dry-run mode, liveness probe, display name extraction) complete the production-ready service.

**Delivers:** A running polling loop with graceful shutdown, error recovery, and restart-safe behavior. Dry-run mode for safe initial deployment. Health/liveness signal for Kubernetes. Clean display names in contacts.

**Implements:** `main.py`, signal handlers (SIGTERM for graceful k8s shutdown), dry-run flag, liveness file or HTTP health check, sender display name extraction from `From` header.

**Avoids:** Silent failures (structured logging throughout), polling loop that does not restart (k8s restartPolicy: Always, confirmed working).

**Research flag:** Skip — standard patterns; well-established approaches for k8s-deployed background workers.

### Phase 5: Deployment and Packaging

**Rationale:** Deploy and validate end-to-end in the home cluster. All integration points (JMAP auth, CardDAV auth, ConfigMap structure, Secret management, container image) are exercised together.

**Delivers:** Docker image pushed to ghcr.io, Kubernetes manifests (Deployment + ConfigMap + Secret template), GitHub Actions CI for image build, README documenting setup and expected behavior.

**Implements:** `Dockerfile` (python:3.13-slim, uv sync --frozen), `k8s/deployment.yaml`, `k8s/configmap.yaml`, `k8s/secret.yaml.template` (gitignored), CI workflow.

**Avoids:** Credentials in git (secret.yaml template only, real values via kubectl), running as root (non-root user in Dockerfile and pod security context), JMAP API token used for CardDAV (separate credentials documented).

**Research flag:** Skip — standard Docker + Kubernetes patterns, no research needed.

### Phase Ordering Rationale

- **Config/Logging before clients:** Both clients depend on configuration. Structured logging must be in place before API calls are debugged.
- **JMAP before CardDAV:** JMAP has a mature library; CardDAV is bespoke. Starting with JMAP builds confidence and delivers the query/discovery layer that CardDAV does not need.
- **CardDAV as a validation gate:** The contact group model risk is too high to defer. Phase 2 must include live Fastmail verification before Phase 3 builds on it. This sequencing prevents a costly rewrite.
- **Workflow after both clients:** `screener.py` has no logic of its own — it orchestrates. It cannot be written meaningfully until both clients are proven.
- **Main loop late:** The outer poller shell is trivial; deferring it avoids premature loop complexity during client development.
- **Deployment last:** Integration testing during Phase 2-3 can run against live Fastmail with direct script calls; full k8s deployment is the final validation.

### Research Flags

**Needs deeper research/validation during planning or execution:**
- **Phase 2 (CardDAV):** KIND:group contact group model must be validated against live Fastmail. Do not proceed to Phase 3 until a contact created via PUT appears in the correct group in the Fastmail web UI AND triggers a Fastmail rule. This is the single most important validation gate in the project.

**Standard patterns (skip research-phase during roadmap planning):**
- **Phase 1 (JMAP foundation):** jmapc source code inspected; patterns verified; pitfalls identified and preventable at code review.
- **Phase 3 (Triage pipeline):** Workflow assembly of validated components; patterns from architecture research are sufficient.
- **Phase 4 (Hardening):** Standard k8s background worker patterns.
- **Phase 5 (Deployment):** Standard Docker + Kubernetes; no novel patterns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Library versions verified via PyPI API and GitHub source inspection. jmapc source code inspected directly. CardDAV library gap is confirmed, not assumed. |
| Features | MEDIUM | HEY Mail and SaneBox analysis from training data (WebSearch unavailable). Feature requirements from PROJECT_BRIEF.md (high confidence). Competitor feature claims should be spot-checked if surprising. |
| Architecture | HIGH | jmapc session management verified from source code. CardDAV protocol is well-specified RFC. Build order derived from component dependencies. Patterns validated by source inspection. |
| Pitfalls | MEDIUM | JMAP/CardDAV protocol pitfalls are from training data knowledge of RFCs. Fastmail-specific behavior (KIND:group model, vCard format) is from training data, not live verification. Pitfall #3 (contact group model) has HIGH recovery cost if wrong — verify in Phase 2. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Fastmail CardDAV group model (critical):** Research identifies KIND:group + MEMBER as the correct approach, but this is from training data, not a verified live Fastmail test. Phase 2 must begin with a manual prototype that proves this works before any pipeline code is written. If CATEGORIES or another model is required, the entire contact group assignment flow must be revised.

- **Fastmail API endpoints (minor):** JMAP host (`api.fastmail.com`) and CardDAV URL (`carddav.fastmail.com/dav/addressbooks/user/<user>/Default/`) are from training data. Verify against the Fastmail developer docs at https://www.fastmail.com/dev/ during Phase 1 setup.

- **Fastmail rate limits (minor):** Fastmail does not publish explicit rate limits. The 5-minute polling interval is conservative. If aggressive testing triggers rate limiting, back off to 10 minutes. Not expected to be an issue at the planned usage volume.

- **jmapc Email/query filter syntax for sender (moderate):** The JMAP `Email/query` filter for "from a specific sender in a specific mailbox" needs to be verified against jmapc's filter models during Phase 1. The `EmailQueryFilterCondition` model in jmapc has a `from_` field — the exact syntax for combined mailbox + sender filters should be tested early.

- **Competitor feature claims (low priority):** Feature research notes WebSearch was unavailable. HEY Mail and SaneBox feature descriptions are from training data. These are directionally correct for product philosophy purposes, but specific UI behavior claims should not be treated as definitive.

## Sources

### Primary (HIGH confidence)
- PyPI JSON API (`pypi.org/pypi/{package}/json`) — verified package versions, upload dates, and dependency trees for all stack components
- GitHub API (`api.github.com`) — verified stars, activity, repository status for jmapc and structlog
- GitHub raw source (`raw.githubusercontent.com`) — jmapc v0.2.23 source code; client session management, API patterns, email/mailbox models verified directly
- Fastmail developer help center — CardDAV server endpoints and auth requirements (via training data reference)
- PROJECT_BRIEF.md — project requirements and scope (in-repo, high confidence)

### Secondary (MEDIUM confidence)
- JMAP Core Specification (RFC 8620) — session resource, method calls, batching, error handling
- JMAP Mail Specification (RFC 8621) — Email/query, Email/get, Email/set, Mailbox operations
- vCard 4.0 Specification (RFC 6350) — KIND:group, MEMBER property for contact groups
- CardDAV Specification (RFC 6352) — ETag handling, PROPFIND, REPORT, addressbook-query
- Fastmail developer documentation (https://www.fastmail.com/dev/) — endpoint verification (training data, not verified against current live docs)
- HEY Mail product documentation and philosophy — feature comparison basis
- Julia Evans blog post on Fastmail JMAP — practical JMAP usage patterns (referenced in PROJECT_BRIEF)

### Tertiary (LOW confidence)
- General CardDAV/vCard interoperability patterns across providers — synthesized from training data; Fastmail-specific behavior requires live validation

---
*Research completed: 2026-02-23*
*Ready for roadmap: yes*
