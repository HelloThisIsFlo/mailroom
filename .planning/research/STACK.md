# Technology Stack: v1.1 Additions

**Project:** Mailroom v1.1 -- Push & Config
**Researched:** 2026-02-25
**Overall confidence:** HIGH

## Context: Existing Stack (DO NOT change)

The v1.0 stack is validated and deployed. These are NOT up for discussion:

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12 | Runtime |
| httpx | 0.28.1 | HTTP client (JMAP + CardDAV) |
| vobject | 0.9.9 | vCard parsing/serialization |
| nameparser | 1.1.3 | Human name parsing for person contacts |
| pydantic-settings | 2.13.1 | Configuration from env vars |
| pydantic | 2.12.5 | Data validation (dependency) |
| structlog | 25.5.0 | Structured JSON logging |
| pytest | 9.0.2 | Testing |
| pytest-httpx | 0.36.0 | Mock httpx in tests |
| ruff | 0.15.2 | Linting + formatting |
| python-dotenv | 1.2.1 | Local .env file loading |

This research covers ONLY what needs to be ADDED or CHANGED for v1.1 features.

---

## New Dependencies

### 1. httpx-sse -- SSE Client for EventSource Push

| Property | Value |
|----------|-------|
| **Package** | httpx-sse |
| **Version** | 0.4.3 (pin to `>=0.4.3,<0.5`) |
| **Purpose** | Parse Server-Sent Events from JMAP EventSource endpoint |
| **Why** | Replaces manual SSE line parsing in the discovery script with a proper SSE decoder that handles event/data/id/retry fields, multi-line data, and edge cases correctly |
| **Confidence** | HIGH |

**Why httpx-sse specifically:**
- The project already uses httpx 0.28.1 for all HTTP. httpx-sse is the official SSE companion listed on httpx's own [Third Party Packages](https://www.python-httpx.org/third_party_packages/) page.
- httpx-sse's only dependency is `httpx` (no version pin) -- zero new transitive dependencies.
- 202 GitHub stars, actively maintained (last release 2025-10-10), 12 contributors.
- Provides `connect_sse()` context manager that wraps `httpx.Client.stream()` and yields properly parsed `ServerSentEvent` objects with `.event`, `.data`, `.id`, `.retry` attributes.
- The existing discovery script (`eventsource_discovery.py`) already uses `httpx.Client.stream()` with manual line parsing. httpx-sse replaces ~40 lines of hand-rolled `parse_sse_event()` with a one-liner.

**Integration pattern:**
```python
from httpx_sse import connect_sse

with httpx.Client(timeout=...) as http:
    with connect_sse(
        http, "GET", url,
        headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
    ) as event_source:
        for sse in event_source.iter_sse():
            if sse.event == "state":
                data = json.loads(sse.data)
                # Check if Email or Mailbox state changed
```

**What NOT to use instead:**
- `sseclient` / `sseclient-py`: These depend on `requests`, not httpx. Adding requests as a second HTTP client is unnecessary weight.
- Raw `response.iter_lines()` parsing: The discovery script already does this and it works, but it's ~40 lines of fragile code that doesn't handle edge cases (multi-line data fields, retry directives, BOM handling). httpx-sse handles these correctly per the W3C SSE spec.

### 2. No Other New Dependencies Required

The remaining v1.1 features (configurable categories, setup script) need **zero new libraries**:

| Feature | Why No New Dependency |
|---------|----------------------|
| **Configurable triage categories** | pydantic-settings 2.13 already supports JSON-encoded complex types from env vars. A `list[TriageCategory]` can be loaded from a single `MAILROOM_CATEGORIES='[...]'` env var. |
| **Setup script (Mailbox/set)** | JMAP `Mailbox/set` create uses the same `JMAPClient.call()` method already in the codebase. It's just a new JSON payload. |
| **Setup script (Contact group create)** | CardDAV group creation is a PUT of a group vCard using the same `httpx` client and `vobject` library already in use. |
| **Debounce logic** | stdlib `threading.Event`, `queue.Queue`, `time.monotonic()` -- no library needed for a simple timer-based debounce. |
| **Exponential backoff** | The SSE reconnect needs simple backoff (1s, 2s, 4s, max 60s). This is 5 lines of `min(base * 2**attempt, max_delay)`. `tenacity` is overkill for a single retry loop. |

---

## Feature-Specific Stack Details

### JMAP EventSource Push Notifications

**What's needed:** A long-lived SSE connection to Fastmail's EventSource endpoint that triggers `workflow.poll()` on state changes.

**Stack involvement:**
- `httpx` (existing) -- HTTP streaming transport
- `httpx-sse` (NEW) -- SSE event parsing
- `threading` (stdlib) -- SSE listener runs in a daemon thread
- `queue.Queue` (stdlib) -- Thread-safe signal from listener to main loop
- `json` (stdlib) -- Parse SSE data payload

**Key technical details from existing research:**
- EventSource URL discovered from JMAP session response (`eventSourceUrl` field) -- already fetched by `JMAPClient.connect()`, just not stored
- Subscribe to `types=Email,Mailbox` (not `*`) to avoid noise from ContactCard/AddressBook changes
- Use `closeafter=no` for persistent connection, `ping=30` for keepalive
- Fastmail wraps events in `{"changed": {...}, "type": "connect|change"}` envelope
- The `connect` event on initial connection contains current state -- useful for confirming connection works but not actionable
- Only `change` events trigger triage passes

**httpx timeout configuration for SSE:**
```python
# SSE needs a long read timeout (server sends keepalives every 30s)
# Set read timeout > ping interval to detect dead connections
timeout = httpx.Timeout(
    connect=30.0,
    read=90.0,    # 3x ping interval -- triggers reconnect if 3 pings missed
    write=30.0,
    pool=30.0,
)
```

**What changes in existing code:**
- `JMAPClient.connect()`: Store `eventSourceUrl` from session (1 line)
- `JMAPClient`: Add `event_source_url` property (3 lines)
- `__main__.py`: New SSE listener function + debounced main loop (~60 lines)
- `config.py`: Add `debounce_seconds: int = 3` (1 line)

### Configurable Triage Categories

**What's needed:** Replace hardcoded label/group/destination mappings with a user-configurable list.

**Stack involvement:**
- `pydantic-settings` (existing) -- JSON-encoded env var for complex types
- `pydantic.BaseModel` (existing) -- Define `TriageCategory` model

**Key technical detail -- pydantic-settings JSON env vars:**

pydantic-settings v2 natively supports complex types from environment variables by treating the value as a JSON-encoded string. No extra library needed.

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class TriageCategory(BaseModel):
    label: str           # e.g. "@ToImbox"
    group: str           # e.g. "Imbox"
    mailbox: str         # e.g. "Inbox" (destination)
    contact_type: str = "company"  # "company" or "person"

class MailroomSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILROOM_")

    categories: list[TriageCategory] = [...]  # default = current hardcoded values
```

**Environment variable format:**
```bash
# Single env var replaces 18 individual label/group/mailbox vars
MAILROOM_CATEGORIES='[
  {"label": "@ToImbox", "group": "Imbox", "mailbox": "Inbox"},
  {"label": "@ToFeed", "group": "Feed", "mailbox": "Feed"},
  {"label": "@ToPaperTrail", "group": "Paper Trail", "mailbox": "Paper Trail"},
  {"label": "@ToJail", "group": "Jail", "mailbox": "Jail"},
  {"label": "@ToPerson", "group": "Imbox", "mailbox": "Inbox", "contact_type": "person"}
]'
```

**Kubernetes ConfigMap:**
```yaml
data:
  MAILROOM_CATEGORIES: |
    [{"label":"@ToImbox","group":"Imbox","mailbox":"Inbox"},...]
```

**Backward compatibility approach:**
- The default value for `categories` should match the current hardcoded behavior exactly
- Existing individual env vars (`MAILROOM_LABEL_TO_IMBOX`, etc.) should continue to work during a transition period, or be dropped entirely since this is a single-user tool where the user controls the upgrade
- The `label_to_group_mapping` property derives from `categories` instead of individual fields

### Setup Script (Mailbox + Contact Group Provisioning)

**What's needed:** A script that creates all required Fastmail mailboxes and contact groups if they don't exist.

**Stack involvement:**
- `JMAPClient.call()` (existing) -- JMAP `Mailbox/set` create
- `CardDAVClient` (existing) -- PUT group vCard to create contact group
- `vobject` (existing) -- Build group vCard
- `argparse` (stdlib) -- CLI for setup script

**JMAP Mailbox/set create (RFC 8621 Section 2.5):**

The `Mailbox/set` method follows standard JMAP `/set` semantics. Creating a mailbox:

```python
# Create a top-level mailbox via existing JMAPClient.call()
responses = jmap.call([
    [
        "Mailbox/set",
        {
            "accountId": jmap.account_id,
            "create": {
                "mb0": {
                    "name": "@ToImbox",
                    "parentId": None,    # top-level
                    "sortOrder": 100,
                    "isSubscribed": True,
                }
            },
        },
        "mc0",
    ]
])
created = responses[0][1].get("created", {})
not_created = responses[0][1].get("notCreated", {})
```

Settable properties on create: `name`, `parentId`, `sortOrder`, `isSubscribed`.
Server-set (read-only): `id`, `role`, `totalEmails`, `unreadEmails`, `totalThreads`, `unreadThreads`, `myRights`.

**Prerequisite:** The Fastmail session must report `mayCreateTopLevelMailbox: true` for the account. This is standard for the primary account owner.

**CardDAV contact group creation:**

Contact groups on Fastmail use Apple-style group vCards (already validated in `CardDAVClient.validate_groups()`):

```python
import vobject, uuid

card = vobject.vCard()
group_uid = str(uuid.uuid4())
card.add("uid").value = group_uid
card.add("fn").value = "Imbox"  # group display name
card.add("x-addressbookserver-kind").value = "group"
# No members initially -- just create the empty group

# PUT to addressbook
resp = http.put(
    f"{addressbook_url}/{group_uid}.vcf",
    content=card.serialize().encode("utf-8"),
    headers={
        "Content-Type": "text/vcard; charset=utf-8",
        "If-None-Match": "*",
    },
)
```

**Script behavior:**
1. Connect JMAP + CardDAV (reuse existing clients)
2. Resolve existing mailboxes (reuse `resolve_mailboxes` but don't raise on missing)
3. For each required mailbox not found: `Mailbox/set` create
4. Validate existing contact groups (reuse `validate_groups` but don't raise on missing)
5. For each required group not found: PUT group vCard
6. Report what was created vs. already existed

**No new dependencies needed.** The setup script uses the same clients and libraries as the main service.

---

## Alternatives Considered

| Decision | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| SSE parsing | httpx-sse | Raw `iter_lines()` parsing | Works (proven in discovery script) but fragile. httpx-sse handles edge cases (multi-line data, BOM, retry field) correctly. Zero new transitive deps since httpx is already installed. |
| SSE parsing | httpx-sse | sseclient / sseclient-py | These depend on `requests`, not httpx. Would add a second HTTP client to the project for no reason. |
| SSE parsing | httpx-sse | aiohttp SSE | Would require async runtime. Mailroom is sync by design (validated decision from v1.0). |
| Debounce | stdlib threading + queue | `tenacity` | tenacity is for retry-with-backoff on function calls. Debounce is "wait for quiet period then trigger" -- different pattern. 5 lines of queue.get(timeout=...) is simpler and more readable. |
| Backoff | Manual `min(base * 2**n, max)` | `tenacity` | SSE reconnect is a single infinite loop with backoff. tenacity adds a decorator abstraction that obscures what's a long-lived connection retry. |
| Config format | JSON env var | YAML config file | pydantic-settings supports JSON from env vars natively. Adding a YAML config file would require a custom settings source or `pydantic-settings-extra-sources`. For a k8s deployment that already uses ConfigMap env vars, JSON-in-env-var is simpler. |
| Config format | JSON env var | env_nested_delimiter | `MAILROOM_CATEGORIES__0__LABEL=@ToImbox` syntax is verbose and unreadable for a list of 5 categories. JSON is cleaner: one env var, one JSON array. |
| Config format | JSON env var | Keep individual env vars | 18 individual env vars for 5 categories is already at the limit. Adding a 6th category means adding 3-4 more vars. JSON array scales linearly. |
| Setup script | CLI script (`python -m mailroom.setup`) | Helm/init-container | Overkill for a single-user tool. A CLI script the user runs once (or on config change) is simpler and more debuggable. |
| Contact group create | CardDAV PUT vCard | JMAP ContactCard/set | Fastmail does NOT support JMAP for contacts yet (validated constraint from v1.0). CardDAV is the only option. |

---

## What NOT to Add

| Technology | Why Not |
|------------|---------|
| `tenacity` | v1.0 research recommended it but it was never used. The retry-safety design (leave triage label, retry next poll) is simpler and proven. SSE reconnect is a simple loop. |
| `asyncio` / `anyio` | SSE listener runs in a daemon thread. The main loop and all business logic remain synchronous. No async runtime needed. |
| `click` / `typer` | Setup script CLI needs `--dry-run` and maybe `--force`. `argparse` is sufficient for 2-3 flags. |
| `pyyaml` / `toml` | Config stays in env vars (k8s ConfigMap). No config file format needed. |
| `jmapc` | v1.0 research recommended it but the project built a thin custom JMAP client on raw httpx instead. That was the right call -- simpler, no GPL dependency, no abandoned-library risk. |
| `lxml` | v1.0 research recommended it for CardDAV XML parsing but the project uses stdlib `xml.etree.ElementTree` instead. That was the right call. |
| `requests` | v1.0 research recommended it for CardDAV but the project uses httpx for everything. That was the right call -- single HTTP client. |

---

## Installation

```bash
# From project root -- one new dependency
uv add httpx-sse

# That's it. No other new dependencies for v1.1.
```

**Updated pyproject.toml dependencies section:**
```toml
dependencies = [
    "httpx",
    "httpx-sse>=0.4.3,<0.5",    # NEW for v1.1
    "nameparser>=1.1.3",
    "pydantic-settings",
    "structlog",
    "vobject>=0.9.9",
]
```

No new dev dependencies needed. `pytest-httpx` can mock SSE streams for testing.

---

## Risk Assessment

### httpx-sse is low risk

- **Beta (0.x)** but the API surface is tiny (one function: `connect_sse`). Breaking changes unlikely.
- **httpx is the transport** -- if httpx-sse were abandoned, the fallback is the raw `iter_lines()` parsing already proven in the discovery script (~40 lines).
- **No transitive dependencies** beyond httpx (already installed).
- **202 stars, 12 contributors, 6 open issues** -- healthy for a focused library.

### Configurable categories via JSON env var is low risk

- **pydantic-settings v2** JSON env var parsing is a documented, well-tested feature. Not experimental.
- **Default values** ensure backward compatibility -- if `MAILROOM_CATEGORIES` is not set, the default matches current v1.0 behavior.
- **Validation at startup** -- pydantic will reject malformed JSON before the service starts.

### Setup script is low risk

- **Mailbox/set create** is standard JMAP (RFC 8621). The existing `JMAPClient.call()` handles it.
- **CardDAV group vCard PUT** uses the same pattern as `create_contact()` in the existing codebase.
- **Idempotent by design** -- checks for existence before creating.

---

## Sources

- [httpx-sse PyPI](https://pypi.org/project/httpx-sse/) -- version 0.4.3, released 2025-10-10 (HIGH confidence)
- [httpx-sse GitHub](https://github.com/florimondmanca/httpx-sse) -- 202 stars, 12 contributors, 6 open issues (HIGH confidence)
- [httpx Third Party Packages](https://www.python-httpx.org/third_party_packages/) -- httpx-sse listed as official companion (HIGH confidence)
- [pydantic-settings docs: complex types from env](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- JSON-encoded env vars for list/dict/model (HIGH confidence)
- [RFC 8621 Section 2.5: Mailbox/set](https://datatracker.ietf.org/doc/html/rfc8621) -- create properties: name, parentId, sortOrder, isSubscribed (HIGH confidence)
- [RFC 8620 Section 7.3: Event Source](https://www.rfc-editor.org/rfc/rfc8620#section-7.3) -- EventSource URL, query params, SSE format (HIGH confidence)
- [Existing EventSource research](../.research/jmap-eventsource/jmap-eventsource.md) -- Fastmail envelope format, observed JMAP types (HIGH confidence)
- [Existing integration sketch](../.research/jmap-eventsource/integration-sketch.md) -- Thread architecture, debounce pattern (HIGH confidence)
- Existing codebase: `pyproject.toml`, `config.py`, `jmap.py`, `carddav.py`, `__main__.py` -- current stack and patterns (HIGH confidence)
