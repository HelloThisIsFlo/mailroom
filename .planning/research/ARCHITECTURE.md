# Architecture Research

**Domain:** Polling-based email automation service (JMAP + CardDAV)
**Researched:** 2026-02-23
**Confidence:** HIGH (library source code inspected directly, protocol specs well-understood)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Kubernetes Pod                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Main Loop (Poller)                      │   │
│  │  while running:                                           │   │
│  │    sleep(interval) -> poll() -> process() -> repeat       │   │
│  └──────────┬───────────────────────────┬────────────────────┘   │
│             │                           │                        │
│  ┌──────────▼──────────┐  ┌─────────────▼─────────────────┐     │
│  │   JMAP Client        │  │   CardDAV Client              │     │
│  │   (jmapc library)    │  │   (requests + vobject)        │     │
│  │                      │  │                               │     │
│  │  - Session mgmt      │  │  - Contact lookup             │     │
│  │  - Email/Query       │  │  - Contact create/update      │     │
│  │  - Mailbox ops       │  │  - Group membership           │     │
│  │  - Label removal     │  │  - vCard serialization        │     │
│  └──────────┬───────────┘  └─────────────┬─────────────────┘     │
│             │                            │                       │
│  ┌──────────▼────────────────────────────▼─────────────────┐     │
│  │                  Screener Workflow                        │     │
│  │                                                          │     │
│  │  1. Find triaged emails (JMAP query by mailbox)          │     │
│  │  2. Extract sender address                               │     │
│  │  3. Upsert contact into group (CardDAV)                  │     │
│  │  4. Sweep sender's Screener emails to destination (JMAP) │     │
│  │  5. Remove triage label from processed email (JMAP)      │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Config + Logging                        │   │
│  │  - Pydantic Settings (env vars / ConfigMap)               │   │
│  │  - structlog (JSON to stdout)                             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌────────────────────┐
│  Fastmail JMAP   │          │  Fastmail CardDAV   │
│  api.fastmail.com│          │  carddav.fastmail.com│
└─────────────────┘          └────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Poller (main loop)** | Periodic execution, graceful shutdown, error recovery | `while` loop with `time.sleep()` and signal handlers |
| **JMAP Client** | All email operations: query, read, move, label | `jmapc` library wrapping Fastmail JMAP API |
| **CardDAV Client** | Contact CRUD, group membership management | `requests` + `vobject` against Fastmail CardDAV |
| **Screener Workflow** | Orchestrates the triage sequence for one sender | Pure business logic calling JMAP + CardDAV clients |
| **Config** | Load settings from env vars / ConfigMap | `pydantic-settings` with validation |
| **Logging** | Structured JSON logs for k8s observability | `structlog` with JSON renderer |

## Recommended Project Structure

```
mailroom/
├── src/
│   └── mailroom/
│       ├── __init__.py
│       ├── __main__.py          # Entry point: python -m mailroom
│       ├── main.py              # Polling loop, signal handling, startup
│       ├── config.py            # Pydantic Settings model
│       ├── logging.py           # structlog configuration
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── jmap.py          # JMAP client wrapper (thin layer over jmapc)
│       │   └── carddav.py       # CardDAV client (requests + vobject)
│       └── workflows/
│           ├── __init__.py
│           └── screener.py      # Screener triage workflow
├── tests/
│   ├── conftest.py
│   ├── test_screener.py
│   ├── test_jmap.py
│   └── test_carddav.py
├── Dockerfile
├── pyproject.toml
└── k8s/
    ├── deployment.yaml
    └── configmap.yaml
```

### Structure Rationale

- **`src/mailroom/`:** Standard src-layout for Python packages. Prevents accidental imports from project root. `python -m mailroom` entry point is k8s-friendly.
- **`clients/`:** Protocol-specific adapters. Each file owns one external API. The rest of the codebase never calls `requests` or `jmapc` directly -- always through these wrappers.
- **`workflows/`:** Business logic separated from protocol concerns. `screener.py` orchestrates the triage sequence. Future workflows (e.g., `List-Unsubscribe` auto-classification) add new files here without touching clients.
- **`config.py`:** Single source of truth for all configuration. Pydantic validates at startup -- fail fast if env vars are missing.
- **No `models/` directory:** This service has no domain models beyond what jmapc and vobject already provide. Adding a models layer would be premature abstraction. If needed later, add it.

## Architectural Patterns

### Pattern 1: Thin Client Wrappers

**What:** Wrap external protocol libraries (`jmapc`, `requests`/`vobject`) in project-specific classes that expose domain operations, not protocol operations.
**When to use:** Always. This is the core architectural boundary.
**Trade-offs:** Slight indirection, but testability and future-proofing are worth it.

**Example:**
```python
# clients/jmap.py -- Domain operations, not JMAP protocol details
class JMAPClient:
    def __init__(self, client: jmapc.Client):
        self._client = client
        self._mailbox_cache: dict[str, str] = {}  # name -> id

    def find_emails_in_mailbox(self, mailbox_name: str) -> list[TriagedEmail]:
        """Find all emails in a mailbox (label), returning sender + email id."""
        mailbox_id = self._resolve_mailbox_id(mailbox_name)
        # EmailQuery + EmailGet in one JMAP request
        ...

    def move_emails_to_mailbox(
        self, email_ids: list[str], from_mailbox: str, to_mailbox: str
    ) -> None:
        """Move emails between mailboxes (labels) via EmailSet."""
        ...

    def remove_mailbox_from_email(self, email_id: str, mailbox_name: str) -> None:
        """Remove a label from an email."""
        ...
```

### Pattern 2: Workflow as Orchestrator

**What:** The workflow module calls client methods in sequence but contains no protocol logic. It is the "script" that says what happens, not how.
**When to use:** For every business operation that spans multiple API calls.
**Trade-offs:** More files, but each is independently testable and replaceable.

**Example:**
```python
# workflows/screener.py
class ScreenerWorkflow:
    def __init__(self, jmap: JMAPClient, carddav: CardDAVClient, config: Settings):
        self.jmap = jmap
        self.carddav = carddav
        self.config = config

    def process_triage_label(self, label_name: str, destination: str) -> int:
        """Process all emails with a triage label. Returns count processed."""
        emails = self.jmap.find_emails_in_mailbox(label_name)
        processed = 0
        for email in emails:
            try:
                self._triage_sender(email, label_name, destination)
                processed += 1
            except Exception:
                log.exception("Failed to triage", sender=email.sender)
                # Leave triage label in place -- retry next poll
        return processed

    def _triage_sender(
        self, email: TriagedEmail, triage_label: str, destination: str
    ) -> None:
        # 1. Add sender to contact group
        self.carddav.ensure_contact_in_group(email.sender, destination)
        # 2. Sweep all Screener emails from this sender
        screener_emails = self.jmap.find_emails_from_sender_in_mailbox(
            email.sender, self.config.screener_mailbox
        )
        self.jmap.move_emails_to_mailbox(
            [e.id for e in screener_emails],
            from_mailbox=self.config.screener_mailbox,
            to_mailbox=destination,
        )
        # 3. For Imbox: also add Inbox label so emails appear immediately
        if destination == self.config.imbox_mailbox:
            self.jmap.add_mailbox_to_emails(
                [e.id for e in screener_emails], "Inbox"
            )
        # 4. Remove triage label from the triggering email
        self.jmap.remove_mailbox_from_email(email.id, triage_label)
```

### Pattern 3: Fail-Open with Retry on Next Poll

**What:** If any step in triage fails, leave the triage label in place and move on. The next poll cycle will retry automatically.
**When to use:** For all operations where idempotency can be guaranteed.
**Trade-offs:** May process the same sender multiple times if CardDAV succeeds but JMAP fails. Contact upsert must be idempotent.

**Critical requirement:** Every operation must be safe to repeat:
- Adding a contact to a group when they are already in it: no-op
- Moving emails that are already in the destination: no-op
- Removing a label that is already removed: no-op

## Data Flow

### Poll Cycle Flow

```
[Timer fires]
    │
    ▼
[JMAP] Query emails in @ToImbox, @ToFeed, @ToPaperTrail, @ToJail mailboxes
    │
    ▼
[For each triage label with emails]
    │
    ▼
[For each unique sender in that label]
    │
    ├──▶ [CardDAV] Find contact by email address
    │       │
    │       ├── Found? Update group membership
    │       └── Not found? Create contact + assign group
    │
    ├──▶ [JMAP] Query all emails from sender in Screener
    │       │
    │       ▼
    │    [JMAP] Email/set: remove Screener mailbox, add destination mailbox
    │       │
    │       ▼
    │    [JMAP] If Imbox: also add Inbox mailbox to swept emails
    │
    └──▶ [JMAP] Email/set: remove triage label from triggering email
           │
           ▼
        [Log] "triaged sender=X to=Feed count=5"
```

### JMAP Session Management

The `jmapc` library handles session management via `functools.cached_property`. Key behaviors discovered from source code inspection:

1. **Session discovery:** First API call triggers `GET https://api.fastmail.com/.well-known/jmap` which returns the Session object (API URL, account ID, capabilities, upload/download URLs).
2. **Session caching:** The Session is cached as a `cached_property`. Subsequent API calls reuse it.
3. **Auto-invalidation:** After each API response, `jmapc` compares `response.session_state` with `cached_session.state`. If they differ, it deletes the cached session, forcing re-discovery on the next request. This is correct JMAP behavior per the spec.
4. **Implication for polling:** Create the `jmapc.Client` once at startup. It handles session lifecycle internally. No need to manage session refresh in application code.

```python
# Session management is handled by jmapc internally.
# Create once, use forever:
client = jmapc.Client.create_with_api_token(
    host="api.fastmail.com",
    api_token=config.api_token,
)
# First call triggers session discovery; subsequent calls reuse it.
# Session auto-refreshes when server state changes.
```

### CardDAV Operations Model

Fastmail CardDAV uses standard protocol at `https://carddav.fastmail.com/dav/addressbooks/user/{username}/Default/`.

**Contact operations are HTTP + vCard:**

```
PROPFIND /dav/addressbooks/user/{user}/Default/   → List all contacts
GET      /dav/addressbooks/user/{user}/Default/{uid}.vcf → Get one contact
PUT      /dav/addressbooks/user/{user}/Default/{uid}.vcf → Create/update contact
DELETE   /dav/addressbooks/user/{user}/Default/{uid}.vcf → Delete contact
REPORT   /dav/addressbooks/user/{user}/Default/   → Search contacts
```

**Group membership in vCard:** Fastmail contact groups use the `X-ADDRESSBOOKSERVER-GROUP` extension (Apple-style groups) or the `MEMBER` property on group vCards. The exact mechanism needs validation during implementation, but the standard Fastmail approach is: each contact group is a vCard with `KIND:group` and `MEMBER:urn:uuid:{contact-uid}` entries.

**Recommended approach:** Use `requests` for HTTP + `vobject` for vCard parsing. Do NOT use the `caldav` library (it is CalDAV-focused; using it for CardDAV would fight its abstractions). Do NOT use `pycarddav` (abandoned, last release 2014).

### Key Data Flows

1. **Triage discovery:** JMAP EmailQuery with `in_mailbox` filter for each triage mailbox. Returns email IDs. Then EmailGet for sender addresses. Batch these into a single JMAP request using jmapc's multi-method support.
2. **Contact upsert:** CardDAV REPORT to search by email address. If found, GET the full vCard, add group membership, PUT back. If not found, create new vCard with group membership, PUT to new URL.
3. **Email sweep:** JMAP EmailQuery with `in_mailbox=Screener AND from=sender@example.com`. Then EmailSet to update `mailbox_ids` (remove Screener, add destination). This is a single JMAP method call for all matching emails.
4. **Label cleanup:** JMAP EmailSet on the triggering email to remove the triage mailbox from its `mailbox_ids`.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user (target) | Single-pod deployment, 5-minute poll interval, no persistence needed |
| 2-5 users | Still single pod, but need per-user config. Would require config refactor to support multiple accounts |
| 10+ users | Would need a queue (Redis/NATS) and worker pattern. Not relevant for this project. |

### Scaling Priorities

1. **First bottleneck:** Rate limiting from Fastmail APIs. Fastmail does not publish explicit rate limits, but aggressive polling (< 1 minute) or large batch operations could trigger throttling. The 5-minute poll interval is conservative and safe.
2. **Second bottleneck:** CardDAV latency. Each contact lookup is a synchronous HTTP REPORT. For a backlog of many unique senders in one poll cycle, this could be slow. Mitigation: process senders sequentially within a poll cycle (not in parallel) to avoid overwhelming CardDAV, and accept that a large initial backlog may take several poll cycles to clear.

## Anti-Patterns

### Anti-Pattern 1: Async for a Polling Service

**What people do:** Use `asyncio` / `aiohttp` because "it's more modern" or "better performance."
**Why it's wrong:** This is a single-user polling service that runs every 5 minutes. Async adds complexity (event loop management, async context managers, library compatibility) with zero benefit. `jmapc` uses synchronous `requests` internally. Adding async would mean either replacing jmapc or wrapping sync calls in executors -- all pain, no gain.
**Do this instead:** Use synchronous Python with `time.sleep()` for the poll loop. Simple, debuggable, matches the library ecosystem.

### Anti-Pattern 2: Building a Plugin System for "Future Extensibility"

**What people do:** Create abstract base classes, registration patterns, and dynamic loading for workflows that do not yet exist.
**Why it's wrong:** YAGNI. The project brief explicitly states v1 is Screener-only. A plugin system adds design constraints before the second use case is understood. It biases future development toward the abstractions chosen today.
**Do this instead:** Keep workflows in a `workflows/` directory with a simple class per workflow. When the second workflow arrives, extract a common interface from the two concrete implementations. The directory structure already supports this.

### Anti-Pattern 3: Caching Contacts Locally

**What people do:** Cache the full address book in memory or SQLite to avoid CardDAV lookups.
**Why it's wrong:** Creates a consistency problem. If contacts are modified outside this service (e.g., via Fastmail web UI), the cache is stale. Cache invalidation for CardDAV is non-trivial (requires sync tokens and periodic full syncs).
**Do this instead:** Always query CardDAV for the authoritative state. A REPORT query for a single email address is fast enough (< 200ms). At 5-minute poll intervals with a handful of triage actions per cycle, this adds negligible overhead.

### Anti-Pattern 4: Treating Fastmail Labels as JMAP Keywords

**What people do:** Assume Fastmail "labels" map to JMAP `keywords` (the `$` prefixed flags).
**Why it's wrong:** Fastmail labels are actually **mailboxes**. An email with the label "@ToImbox" has that mailbox ID in its `mailbox_ids` dict. JMAP keywords are for flags like `$seen`, `$flagged`, `$draft`. Confusing these means queries return nothing.
**Do this instead:** Use `EmailQuery` with `in_mailbox` filter (not `has_keyword`). Use `EmailSet` to modify `mailbox_ids` (not `keywords`). Resolve label names to mailbox IDs via `MailboxQuery` at startup.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Fastmail JMAP (`api.fastmail.com`) | `jmapc` library, Bearer token auth | Session auto-managed. Use `create_with_api_token`. Host is `api.fastmail.com`. |
| Fastmail CardDAV (`carddav.fastmail.com`) | `requests` + Basic auth, `vobject` for vCard | CardDAV requires Basic auth (not Bearer). May need separate credentials (app password). Validate during implementation. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| main.py <-> workflows/ | Direct method calls | Main loop instantiates workflow, calls `process_triage_label()` per label |
| workflows/ <-> clients/ | Direct method calls | Workflow calls domain-level methods on client wrappers |
| clients/jmap.py <-> jmapc | Library API | Thin wrapper; translates domain concepts to jmapc method calls |
| clients/carddav.py <-> requests | HTTP calls | Builds WebDAV XML requests, parses vCard responses |
| config.py <-> environment | `pydantic-settings` reads env vars | Kubernetes ConfigMap/Secret -> env vars -> Pydantic model |

### JMAP Mailbox ID Resolution

A critical implementation detail: JMAP operations require mailbox IDs (opaque strings), not human-readable names. The JMAP client wrapper must resolve names to IDs at startup.

```python
# Resolve at startup, cache for the process lifetime:
# MailboxQuery -> list all mailboxes -> build name->id map
# "@ToImbox" -> "Ma1b2c3d4"
# "Screener" -> "Me5f6g7h8"
# "Inbox"    -> "Mi9j0k1l2"
```

This mapping should be refreshed if the JMAP session state changes (jmapc handles session invalidation, but the mailbox cache is in application code). Pragmatic approach: rebuild the mailbox map once per poll cycle. It is a single lightweight JMAP call.

## Suggested Build Order

Based on component dependencies:

1. **Config + Logging** -- Foundation. Everything depends on configuration being loaded and logs being structured. Zero external API calls needed to build and test this.
2. **JMAP Client wrapper** -- Depends on config (for API token, host). Can be integration-tested against Fastmail immediately. Start with mailbox resolution and email querying.
3. **CardDAV Client** -- Depends on config (for credentials, URL). Independent of JMAP client. Can be built and tested in parallel with JMAP work if desired.
4. **Screener Workflow** -- Depends on both clients. This is the business logic that wires everything together.
5. **Main Loop (Poller)** -- Depends on workflow. The outermost shell: signal handling, sleep loop, error recovery.
6. **Docker + Kubernetes** -- Depends on everything working. Containerize and deploy.

**Key insight:** Steps 2 and 3 are independent and can be developed in parallel. Step 4 is where the real integration happens. Step 5 is trivial once step 4 works.

## Sources

- `jmapc` library source code (v0.2.23) -- installed and inspected directly. Client session management, API patterns, email/mailbox models all verified from source.
- `jmapc` dependencies: `requests`, `dataclasses-json`, `sseclient`, `brotli`
- `caldav` library source code (v2.2.6) -- inspected for CardDAV support. Confirmed CalDAV-focused; has WebDAV primitives but not suitable as a CardDAV client library.
- `vobject` (v0.9.9) -- available on PyPI for vCard parsing/generation
- `pycarddav` (v0.7.0) -- exists but abandoned (last release 2014)
- JMAP protocol: session management via `.well-known/jmap`, session state auto-invalidation pattern confirmed in jmapc source
- Fastmail API endpoints: `api.fastmail.com` (JMAP), `carddav.fastmail.com` (CardDAV) -- from training data, needs validation during implementation (MEDIUM confidence)
- CardDAV protocol: standard WebDAV + vCard, PROPFIND/GET/PUT/REPORT methods (HIGH confidence, well-established standard)

---
*Architecture research for: Polling-based Fastmail email automation service*
*Researched: 2026-02-23*
