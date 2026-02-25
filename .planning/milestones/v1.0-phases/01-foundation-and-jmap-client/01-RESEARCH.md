# Phase 1: Foundation and JMAP Client - Research

**Researched:** 2026-02-24
**Domain:** JMAP email protocol, Python project scaffolding, configuration management, structured logging
**Confidence:** HIGH

## Summary

Phase 1 establishes the Python project foundation and a working JMAP client for Fastmail. The JMAP protocol (RFC 8620/8621) is a JSON-over-HTTPS API that replaces IMAP, and Fastmail is its reference implementation. The core operations needed -- session discovery, mailbox resolution, email querying, sender extraction, and batch email moves via label patching -- are well-specified and straightforward to implement with a thin client over `httpx`.

The Python ecosystem provides mature, well-documented libraries for every supporting concern: `pydantic-settings` for typed environment variable configuration with prefix support, `structlog` for structured JSON logging, `uv` for fast dependency management, and `ruff` for linting/formatting. All are actively maintained, permissively licensed, and widely adopted.

**Primary recommendation:** Build a thin JMAP client directly on `httpx` rather than using the `jmapc` third-party library. The JMAP protocol is simple (JSON POST requests), the project needs only 5-6 JMAP methods, `jmapc` is GPL-3.0 licensed, has only 52 GitHub stars, and adds unnecessary abstraction. Fastmail's own reference samples demonstrate that a complete JMAP client is ~100 lines of Python.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- All env vars prefixed with `MAILROOM_` (e.g. `MAILROOM_JMAP_TOKEN`, `MAILROOM_POLL_INTERVAL`)
- Sensible defaults for non-credential config: poll interval = 5 min, standard label names (@ToImbox, @ToFeed, @ToPaperTrail, @ToJail), standard group names (Imbox, Feed, Paper Trail, Jail)
- Credentials are required -- service fails if JMAP token or CardDAV password is missing
- Log level controlled via `MAILROOM_LOG_LEVEL` env var (default: info)
- Fail fast if any configured triage labels don't exist as mailboxes in Fastmail -- catches typos before polling starts
- Validate that all 4 contact groups exist via CardDAV at startup -- catches setup issues early
- Always log resolved config summary at startup (label names, group names, poll interval) at info level so it's visible in kubectl logs
- Structured JSON logs
- Info level: only log when actually processing a triage email (silent when nothing to do)
- Debug level: log one line per poll cycle ("poll: 0 triage emails found")
- Always log resolved config at startup regardless of level
- Detail level for triage actions at Claude's discretion
- Python 3.12+
- uv for dependency management (pyproject.toml + uv.lock)
- ruff for linting and formatting (configured in pyproject.toml)
- Layer-based module structure: `clients/` (JMAP, CardDAV), `workflows/` (screener), `core/` (config, logging)
- pytest scaffold from day one (tests/ directory, pytest in dev deps, conftest.py)

### Claude's Discretion
- Label-to-group mapping config structure (individual env vars vs structured)
- Fastmail username: config value vs derive from JMAP session
- Auth failure behavior at startup (crash vs retry with backoff)
- Mid-run Fastmail unreachable behavior (log and retry next cycle vs crash)
- Module layout details (exact file names, whether to use src/ prefix)
- Triage action log detail level (summary line vs step-by-step)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| JMAP-01 | Authenticate with Fastmail JMAP API using Bearer token | Session discovery via `https://api.fastmail.com/jmap/session` with `Authorization: Bearer {token}` header. Returns account ID and API URL. |
| JMAP-02 | Resolve mailbox names to mailbox IDs (Screener, @ToImbox, etc.) | `Mailbox/get` with `ids: null` returns all mailboxes. Match by `name` property. Role-based lookup only works for standard roles (inbox, drafts). Custom mailboxes must match by name. |
| JMAP-03 | Query emails by mailbox/label to find triaged emails | `Email/query` with `filter: { inMailbox: "mailboxId" }` returns email IDs. Supports sort, limit, position for pagination. |
| JMAP-04 | Extract sender email address from a triaged email | `Email/get` with `properties: ["from"]` returns `from` array of `{name, email}` objects. First element is the sender. |
| JMAP-05 | Remove triage label using JMAP patch syntax | `Email/set` with `update: { "emailId": { "mailboxIds/triageLabelId": null } }` removes the label while preserving other labels. |
| JMAP-06 | Query Screener for all emails from a specific sender | `Email/query` with `filter: { inMailbox: "screenerId", from: "sender@example.com" }` returns matching emails. May need pagination for large result sets. |
| JMAP-07 | Batch-update swept emails (remove Screener, add destination) | `Email/set` with multiple entries in `update` map. Each entry patches `mailboxIds/screenerId: null, mailboxIds/destinationId: true`. Subject to `maxObjectsInSet` (minimum 500). |
| JMAP-08 | Add Inbox label when destination is Imbox | Same `Email/set` patch: also include `mailboxIds/inboxId: true` when the destination mailbox is Imbox. |
| CONF-01 | All label/group names configurable via environment variables | `pydantic-settings` with `env_prefix='MAILROOM_'` provides typed, validated config from env vars with defaults. |
| CONF-02 | Polling interval configurable via environment variable | `MAILROOM_POLL_INTERVAL` with default `300` (5 min), validated as positive integer by pydantic. |
| CONF-03 | Fastmail credentials from environment variables | Required fields without defaults in pydantic-settings model. Service fails at startup if missing. |
| LOG-01 | Structured JSON logs with action, sender, timestamp, success/failure | `structlog` with `JSONRenderer`, `TimeStamper(fmt="iso")`, and `add_log_level` processors. Bind action/sender context per operation. |
| LOG-02 | Errors logged with enough context to diagnose without cluster access | `structlog` exception processors (`format_exc_info`, `dict_tracebacks`) serialize full tracebacks as structured JSON fields. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.28.1 | HTTP client for JMAP API calls | Modern, sync+async, HTTP/2 support, MIT licensed. Used instead of `requests` for modern Python. |
| pydantic-settings | 2.13.x | Configuration from environment variables | Official Pydantic companion. Type-safe env var parsing with prefix support, validation, and defaults. |
| structlog | 25.5.0 | Structured JSON logging | De facto standard for structured logging in Python. MIT/Apache-2.0. Processors pipeline, JSON output, dev console mode. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.x | Data validation (dependency of pydantic-settings) | Pulled in automatically. Also useful for JMAP response models if desired. |
| ruff | latest | Linting and formatting | Configured in pyproject.toml. Replaces black + isort + flake8. |
| pytest | latest | Test framework | Dev dependency. Scaffold from day one per user decision. |
| pytest-httpx | latest | Mock httpx calls in tests | Dev dependency for testing JMAP client without live API. |

### Alternatives Considered
| Instead of | Could Use | Why Not |
|------------|-----------|---------|
| httpx (thin client) | jmapc | GPL-3.0 license, 52 stars, uses `requests` (not httpx), adds unnecessary abstraction for 5-6 JMAP methods. JMAP is simple JSON-over-HTTP. |
| httpx (thin client) | python-jmap (boopmail) | Archived/abandoned since April 2024. MIT but unmaintained. |
| pydantic-settings | python-dotenv + os.environ | No type validation, no prefix support, no defaults management. Hand-rolling what pydantic-settings does out of the box. |
| structlog | python-json-logger | structlog has richer processor pipeline, better dev experience, and is more actively maintained. |
| httpx | requests | httpx is the modern successor. Better async support, HTTP/2, similar API. |

**Installation:**
```bash
uv add httpx pydantic-settings structlog
uv add --dev ruff pytest pytest-httpx
```

## Architecture Patterns

### Recommended Project Structure
```
mailroom/
├── pyproject.toml          # Project metadata, dependencies, ruff config
├── uv.lock                 # Locked dependencies
├── src/
│   └── mailroom/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py       # Settings (pydantic-settings BaseSettings)
│       │   └── logging.py      # structlog configuration
│       ├── clients/
│       │   ├── __init__.py
│       │   └── jmap.py         # Thin JMAP client over httpx
│       └── workflows/          # Empty in Phase 1, placeholder
│           └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Shared fixtures
│   ├── test_config.py
│   ├── test_jmap_client.py
│   └── test_logging.py
└── .python-version             # 3.12
```

Note: Using `src/` layout is recommended for Python packages to avoid import confusion between the project root and the package. The user's decision says "whether to use src/ prefix" is at Claude's discretion -- **use src/ layout** because it prevents accidental imports from the project root and is the modern Python standard.

### Pattern 1: Thin JMAP Client
**What:** A small class wrapping httpx that handles session discovery, authentication, and JMAP method calls. Not a full protocol implementation -- just the methods mailroom needs.
**When to use:** Always. This is the primary interface to Fastmail.
**Example:**
```python
# Source: Adapted from Fastmail JMAP-Samples/python3/tiny_jmap_library.py
# and https://jmap.io/crash-course.html
import httpx
from dataclasses import dataclass

@dataclass
class JMAPSession:
    api_url: str
    account_id: str
    headers: dict[str, str]

class JMAPClient:
    def __init__(self, token: str, hostname: str = "api.fastmail.com"):
        self._token = token
        self._hostname = hostname
        self._http = httpx.Client(
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            }
        )
        self._session: JMAPSession | None = None

    def connect(self) -> JMAPSession:
        """Discover session: account ID, API URL."""
        resp = self._http.get(f"https://{self._hostname}/jmap/session")
        resp.raise_for_status()
        data = resp.json()
        account_id = data["primaryAccounts"]["urn:ietf:params:jmap:mail"]
        self._session = JMAPSession(
            api_url=data["apiUrl"],
            account_id=account_id,
            headers=dict(self._http.headers),
        )
        return self._session

    def call(self, method_calls: list) -> list:
        """Execute JMAP method calls. Returns methodResponses."""
        assert self._session is not None, "Must call connect() first"
        payload = {
            "using": [
                "urn:ietf:params:jmap:core",
                "urn:ietf:params:jmap:mail",
            ],
            "methodCalls": method_calls,
        }
        resp = self._http.post(self._session.api_url, json=payload)
        resp.raise_for_status()
        return resp.json()["methodResponses"]
```

### Pattern 2: Mailbox Resolution at Startup
**What:** Fetch all mailboxes once at startup, build a name-to-ID map, and validate that all configured mailboxes exist.
**When to use:** At service startup, before any email processing.
**Example:**
```python
# Source: JMAP spec (https://jmap.io/spec-mail.html) Mailbox/get
def resolve_mailboxes(client: JMAPClient, required_names: list[str]) -> dict[str, str]:
    """Returns {name: mailbox_id} for all required mailboxes."""
    responses = client.call([
        ["Mailbox/get", {"accountId": client.account_id, "ids": None}, "m0"]
    ])
    mailbox_list = responses[0][1]["list"]
    name_to_id = {mb["name"]: mb["id"] for mb in mailbox_list}

    # Validate all required mailboxes exist
    missing = [n for n in required_names if n not in name_to_id]
    if missing:
        raise ValueError(f"Mailboxes not found in Fastmail: {missing}")

    return {n: name_to_id[n] for n in required_names}
```

### Pattern 3: JMAP Patch Syntax for Label Operations
**What:** Use patch paths to add/remove individual mailbox labels without replacing the entire mailboxIds map.
**When to use:** Every email move/relabel operation.
**Example:**
```python
# Source: RFC 8620 Section 5.3, JMAP Mail spec, jmap.io/client.html
# Remove @ToImbox label and add Imbox + Inbox labels
def build_move_patches(
    email_ids: list[str],
    remove_mailbox_id: str,
    add_mailbox_ids: list[str],
) -> dict:
    """Build Email/set update map for batch move."""
    updates = {}
    for email_id in email_ids:
        patch = {f"mailboxIds/{remove_mailbox_id}": None}
        for add_id in add_mailbox_ids:
            patch[f"mailboxIds/{add_id}"] = True
        updates[email_id] = patch
    return updates

# Usage in Email/set call:
# ["Email/set", {
#     "accountId": account_id,
#     "update": build_move_patches(email_ids, screener_id, [imbox_id, inbox_id])
# }, "e0"]
```

### Pattern 4: Configuration with pydantic-settings
**What:** Type-safe configuration loaded from MAILROOM_-prefixed environment variables.
**When to use:** At application startup.
**Example:**
```python
# Source: pydantic-settings docs (https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
from pydantic_settings import BaseSettings, SettingsConfigDict

class MailroomSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAILROOM_",
        case_sensitive=False,
    )

    # Required -- no default, fails if missing
    jmap_token: str

    # Defaults matching user's existing Fastmail setup
    poll_interval: int = 300  # 5 minutes in seconds
    log_level: str = "info"

    # Triage label names (Fastmail mailbox names)
    label_to_imbox: str = "@ToImbox"
    label_to_feed: str = "@ToFeed"
    label_to_paper_trail: str = "@ToPaperTrail"
    label_to_jail: str = "@ToJail"

    # Destination group names
    group_imbox: str = "Imbox"
    group_feed: str = "Feed"
    group_paper_trail: str = "Paper Trail"
    group_jail: str = "Jail"
```

### Pattern 5: structlog JSON Logging
**What:** Production JSON logging with dev-friendly console output during development.
**When to use:** Module-level configuration at application startup.
**Example:**
```python
# Source: structlog docs (https://www.structlog.org/en/stable/logging-best-practices.html)
import sys
import structlog

def configure_logging(log_level: str = "info") -> None:
    """Configure structlog for JSON output (prod) or console (dev)."""
    import logging
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
    ]

    if sys.stderr.isatty():
        # Development: pretty console output
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]
    else:
        # Production (Docker/k8s): structured JSON
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Usage:
# log = structlog.get_logger()
# log.info("email_moved", action="sweep", sender="alice@example.com",
#          destination="Imbox", count=5)
# Output: {"event":"email_moved","action":"sweep","sender":"alice@example.com",
#          "destination":"Imbox","count":5,"level":"info","timestamp":"2026-02-24T..."}
```

### Anti-Patterns to Avoid
- **Hardcoding mailbox IDs:** Fastmail mailbox IDs are opaque strings that may change. Always resolve by name at startup.
- **One HTTP request per email:** JMAP supports batching. Always batch Email/set updates into a single request.
- **Replacing entire mailboxIds map:** Use patch syntax (`mailboxIds/id: true|null`) to add/remove individual labels. Replacing the whole map risks removing labels you don't know about.
- **Polling without rate awareness:** Fastmail has no documented rate limits for JMAP, but be respectful. 5-minute polling is fine. Don't implement tight retry loops.
- **Storing session/account ID permanently:** The session endpoint returns current values. Fetch at startup, don't cache across restarts.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Environment variable parsing with types | Custom env parser, os.environ + manual casting | pydantic-settings | Handles prefix, type coercion, validation, defaults, and required field detection |
| Structured JSON log formatting | Custom JSON formatter on stdlib logging | structlog | Processor pipeline, ISO timestamps, exception serialization, dev/prod mode switching |
| JMAP session discovery | Manual URL construction | Fetch `/.well-known/jmap` or `/jmap/session` endpoint | The session object contains API URL, account ID, capabilities -- all needed for method calls |
| HTTP retry logic | Custom retry loops with sleep | httpx built-in or tenacity | Edge cases: exponential backoff, jitter, timeout handling |

**Key insight:** JMAP is deliberately simple -- it's just JSON POST to one URL. The protocol does not warrant a heavy client library. A ~100-line thin wrapper over httpx covers all Phase 1 needs. The complexity is in the business logic (which emails to move where), not the protocol.

## Common Pitfalls

### Pitfall 1: Mailbox Name Collision
**What goes wrong:** Searching for mailbox "Inbox" by name might return a child mailbox named "Inbox" under another folder, or custom mailboxes with similar names.
**Why it happens:** JMAP mailbox names are not globally unique -- only unique within a parent. Multiple mailboxes could have the same `name` if they have different `parentId` values.
**How to avoid:** For standard roles (inbox), use the `role` property. For custom mailboxes like Screener and @ToImbox, match by exact `name` and optionally verify `parentId` is null (top-level). Log all resolved mailboxes at startup.
**Warning signs:** Wrong emails being moved, unexpected mailbox count at startup.

### Pitfall 2: Email Must Always Belong to at Least One Mailbox
**What goes wrong:** Removing all labels from an email (setting every mailboxIds entry to null) violates the JMAP spec and will be rejected by the server.
**Why it happens:** JMAP requires "An Email MUST belong to one or more Mailboxes at all times" (RFC 8621).
**How to avoid:** Always add the destination mailbox label before or simultaneously with removing the source label. Use a single Email/set call that both adds and removes in one patch.
**Warning signs:** `invalidPatch` or `invalidProperties` errors from Email/set.

### Pitfall 3: Session Endpoint is Not the API Endpoint
**What goes wrong:** Sending JMAP method calls to `https://api.fastmail.com/jmap/session` instead of the `apiUrl` returned by the session.
**Why it happens:** Confusing the session discovery URL with the API URL.
**How to avoid:** Always read `apiUrl` from the session response and use that for all subsequent method calls. For Fastmail, session is at `/jmap/session`, API is typically at `/jmap/api/`.
**Warning signs:** HTTP 404 or 405 errors on method calls.

### Pitfall 4: Pagination on Large Mailboxes
**What goes wrong:** Email/query returns only the first page of results, missing emails from prolific senders in the Screener.
**Why it happens:** JMAP Email/query has a default limit and returns paginated results. If a sender has 500+ emails in Screener, you need multiple pages.
**How to avoid:** Check `total` in the query response against the number of IDs returned. If `len(ids) < total`, fetch additional pages using `position` or `anchor`/`anchorOffset`.
**Warning signs:** Only some of a sender's emails get moved during sweep.

### Pitfall 5: GPL-3.0 License Contamination
**What goes wrong:** Using `jmapc` (GPL-3.0) in the project forces the entire project to be GPL-3.0.
**Why it happens:** GPL-3.0 copyleft requires derivative works to use the same license.
**How to avoid:** Don't use `jmapc`. Build a thin client on `httpx` (MIT licensed). All other recommended libraries are MIT or Apache-2.0.
**Warning signs:** License audit failure, inability to change project license later.

### Pitfall 6: Result Reference Path Errors
**What goes wrong:** Back-references between chained JMAP method calls fail silently or return empty results.
**Why it happens:** The JSON Pointer path in the result reference doesn't match the actual response structure. For example, using `/ids` when the actual path is `/ids/*`.
**How to avoid:** Start with separate requests to verify response shapes, then combine with result references. The path format follows RFC 6901 JSON Pointer with `/` for JMAP's glob syntax `/*`.
**Warning signs:** Empty ID lists in subsequent method calls, unexpected null responses.

## Code Examples

Verified patterns from official sources:

### JMAP Session Discovery (Fastmail)
```python
# Source: https://www.fastmail.com/dev/ and https://jmap.io/crash-course.html
import httpx

def discover_session(token: str) -> dict:
    """Fetch JMAP session from Fastmail."""
    resp = httpx.get(
        "https://api.fastmail.com/jmap/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    session = resp.json()
    return {
        "api_url": session["apiUrl"],
        "account_id": session["primaryAccounts"]["urn:ietf:params:jmap:mail"],
    }
```

### Email/query with Filter and Email/get Chained
```python
# Source: JMAP spec (https://jmap.io/spec-mail.html) and
# Fastmail JMAP-Samples/python3/top-ten.py
method_calls = [
    ["Email/query", {
        "accountId": account_id,
        "filter": {"inMailbox": screener_id, "from": "sender@example.com"},
        "sort": [{"property": "receivedAt", "isAscending": False}],
        "limit": 100,
    }, "q0"],
    ["Email/get", {
        "accountId": account_id,
        "#ids": {"resultOf": "q0", "name": "Email/query", "path": "/ids"},
        "properties": ["id", "from", "subject", "receivedAt", "mailboxIds"],
    }, "g0"],
]
```

### Batch Email Move with Patch Syntax
```python
# Source: RFC 8620 Section 5.3, JMAP client guide (https://jmap.io/client.html)
# Move emails from Screener to Imbox, add Inbox label, remove Screener label
update_map = {}
for email_id in email_ids:
    update_map[email_id] = {
        f"mailboxIds/{screener_id}": None,      # Remove Screener label
        f"mailboxIds/{imbox_id}": True,          # Add Imbox label
        f"mailboxIds/{inbox_id}": True,          # Add Inbox label (for Imbox dest)
    }

method_calls = [
    ["Email/set", {
        "accountId": account_id,
        "update": update_map,
    }, "s0"],
]
```

### pydantic-settings with MAILROOM_ Prefix
```python
# Source: pydantic-settings docs (https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILROOM_")

    jmap_token: str          # Required: MAILROOM_JMAP_TOKEN
    poll_interval: int = 300  # Optional: MAILROOM_POLL_INTERVAL (default 5 min)
    log_level: str = "info"   # Optional: MAILROOM_LOG_LEVEL

# Instantiation validates and fails fast on missing required fields:
# settings = Settings()  # raises ValidationError if MAILROOM_JMAP_TOKEN not set
```

### structlog Bound Logger with Context
```python
# Source: structlog docs (https://www.structlog.org/en/stable/logging-best-practices.html)
import structlog

log = structlog.get_logger()

# Bind context for a triage operation
op_log = log.bind(action="sweep", sender="alice@example.com")
op_log.info("querying_screener", mailbox="Screener")
op_log.info("emails_found", count=12)
op_log.info("move_complete", destination="Imbox", moved=12, inbox_label_added=True)

# Output (JSON):
# {"event":"querying_screener","action":"sweep","sender":"alice@example.com",
#  "mailbox":"Screener","level":"info","timestamp":"2026-02-24T10:30:00Z"}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| IMAP + IDLE for email automation | JMAP (RFC 8620/8621) over HTTPS | 2019 (RFC published) | Simpler, JSON-based, supports batching and result references |
| `requests` library for HTTP | `httpx` for HTTP | 2020+ | Modern API, async support, HTTP/2, better timeout handling |
| `python-dotenv` + `os.environ` | `pydantic-settings` | 2023 (v2 release) | Type-safe, validated, prefix support, composable |
| `logging` + `python-json-logger` | `structlog` | 2013+ (mature) | Processor pipeline, better dev experience, native JSON |
| pip + requirements.txt | uv + pyproject.toml + uv.lock | 2024 | 10-100x faster, lockfile, replaces pip/poetry/pyenv |
| black + isort + flake8 | ruff | 2023+ | Single tool, 10-100x faster, replaces all three |

**Deprecated/outdated:**
- `python-jmap` (boopmail): Archived April 2024, unmaintained
- `jmapc`: Active but GPL-3.0, uses deprecated tooling (poetry, black, flake8)
- Basic Auth for Fastmail JMAP: Deprecated in favor of Bearer token authentication

## Open Questions

1. **maxObjectsInSet on Fastmail**
   - What we know: JMAP spec says minimum 500, Fastmail likely supports at least that
   - What's unclear: Exact Fastmail limit not documented publicly
   - Recommendation: Default to batches of 100 emails per Email/set call. If a sender has 500+ emails in Screener, page through with multiple requests. Test against live API in Phase 1.

2. **Deriving Fastmail username from session**
   - What we know: The session response includes account information. The `Identity/get` method returns email addresses associated with the account.
   - What's unclear: Whether the primary email is reliably extractable from session data
   - Recommendation: Start without needing the username. If needed later (Phase 2 CardDAV), derive from session or add a config value. This is marked as Claude's discretion.

3. **Fastmail rate limits for JMAP**
   - What we know: No public documentation of rate limits. 5-minute polling is extremely conservative.
   - What's unclear: Whether rapid batch operations (e.g., moving 500 emails) trigger rate limiting
   - Recommendation: Implement respectful batching (100 per set call, no tight loops). Handle HTTP 429 responses with exponential backoff if encountered.

4. **Email/query `from` filter exact behavior**
   - What we know: JMAP spec defines `from` filter for Email/query but behavior may vary (substring vs exact match)
   - What's unclear: Whether Fastmail's `from` filter does exact email address match or substring/header match
   - Recommendation: Test against live Fastmail in Phase 1. If `from` filter is not precise enough, fall back to Email/query by mailbox + Email/get to filter sender client-side.

## Sources

### Primary (HIGH confidence)
- [JMAP Core Specification (RFC 8620)](https://www.rfc-editor.org/rfc/rfc8620.html) - PatchObject syntax, /set method, capabilities, maxObjectsInSet
- [JMAP Mail Specification (RFC 8621)](https://jmap.io/spec-mail.html) - Mailbox/get, Email/query, Email/get, Email/set, mailboxIds semantics
- [JMAP Crash Course](https://jmap.io/crash-course.html) - Session discovery, request structure, result references
- [Fastmail API Documentation](https://www.fastmail.com/dev/) - Session endpoint, Bearer token auth, Fastmail-specific details
- [structlog documentation (v25.5.0)](https://www.structlog.org/en/stable/) - JSONRenderer, processors, make_filtering_bound_logger, best practices
- [pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) - BaseSettings, env_prefix, SettingsConfigDict

### Secondary (MEDIUM confidence)
- [Fastmail JMAP-Samples (GitHub)](https://github.com/fastmail/JMAP-Samples) - Official Python samples, tiny_jmap_library.py reference implementation
- [jmapc (GitHub)](https://github.com/smkent/jmapc) - API coverage reference, v0.2.23, GPL-3.0
- [Julia Evans: Implementing focus-and-reply for Fastmail](https://jvns.ca/blog/2020/08/18/implementing--focus-and-reply--for-fastmail/) - Practical JMAP/Fastmail patterns, session discovery
- [Nathan Grigg: Fastmail JMAP backup](https://nathangrigg.com/2021/08/fastmail-backup/) - 142-line Python JMAP client, pagination pattern
- [demo-fastmail-api-jmap (GitHub)](https://github.com/joelparkerhenderson/demo-fastmail-api-jmap) - Mailbox name vs role filtering gotcha, curl examples
- [JMAP Client Guide](https://jmap.io/client.html) - Batch updates, optimistic UI, delta sync patterns
- [uv documentation](https://docs.astral.sh/uv/guides/projects/) - Project init, dependency management, lockfile
- [ruff documentation](https://docs.astral.sh/ruff/configuration/) - pyproject.toml configuration, rule selection

### Tertiary (LOW confidence)
- Fastmail rate limits: No public documentation found. Assumed reasonable based on community reports of no issues with moderate polling.
- Email/query `from` filter precision: Spec says "Looks for the text in the From header" which suggests substring match, not exact email match. Needs live testing.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries verified via official docs and Context7. Versions confirmed on PyPI.
- Architecture: HIGH - JMAP protocol is well-specified via RFCs. Project structure follows Python community standards.
- Pitfalls: MEDIUM - Most pitfalls from spec reading and community reports. Some (rate limits, from filter) need live Fastmail testing.

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (stable domain, 30 days)
