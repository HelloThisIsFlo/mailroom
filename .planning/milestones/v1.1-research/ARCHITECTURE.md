# Architecture: v1.1 Push, Configurable Categories, and Setup Script

**Domain:** Integrating JMAP EventSource push, configurable triage categories, and Fastmail setup script into an existing email triage service
**Researched:** 2026-02-25
**Confidence:** HIGH (codebase fully inspected, RFC 8620 EventSource spec verified, Fastmail SSE behavior empirically observed via discovery script, pydantic-settings capabilities verified via official docs, existing architecture well-understood from 8,666 LOC inspection)

## Existing Architecture (As-Is)

```
                    +-----------------------------------------+
                    |           __main__.py                    |
                    |                                         |
                    |   main()                                |
                    |     settings = MailroomSettings()        |
                    |     jmap.connect()                       |
                    |     carddav.connect()                    |
                    |     resolve_mailboxes()                  |
                    |     validate_groups()                    |
                    |     workflow = ScreenerWorkflow(...)      |
                    |     start_health_server()                |
                    |                                         |
                    |     while not shutdown:                  |
                    |       workflow.poll()          <-- FIXED SLEEP LOOP
                    |       sleep(poll_interval)               |
                    +-----------------------------------------+
                         |                    |
            +------------+                    +------------+
            |                                              |
   +--------v---------+                     +--------------v------+
   |  JMAPClient       |                     |  CardDAVClient       |
   |  (httpx)          |                     |  (httpx + vobject)   |
   |                   |                     |                      |
   |  connect()        |                     |  connect()           |
   |  call()           |                     |  validate_groups()   |
   |  resolve_mailboxes|                     |  search_by_email()   |
   |  query_emails()   |                     |  create_contact()    |
   |  get_email_senders|                     |  add_to_group()      |
   |  remove_label()   |                     |  upsert_contact()    |
   |  batch_move()     |                     |  check_membership()  |
   +-------------------+                     +----------------------+
            |                                              |
            v                                              v
   Fastmail JMAP API                            Fastmail CardDAV API
   api.fastmail.com                             carddav.fastmail.com
```

### Current Component Boundaries

| Component | File | Responsibility |
|-----------|------|----------------|
| **Entry point** | `__main__.py` | Startup sequence, fixed-interval poll loop, signal handling, health server |
| **JMAP Client** | `clients/jmap.py` | Session discovery, mailbox resolution, email query/move/label ops (httpx) |
| **CardDAV Client** | `clients/carddav.py` | PROPFIND discovery, contact search/create/update, group membership (httpx + vobject) |
| **Screener Workflow** | `workflows/screener.py` | Triage orchestration: collect, detect conflicts, process senders |
| **Config** | `core/config.py` | `MailroomSettings` (pydantic-settings), flat env vars, derived properties |
| **Logging** | `core/logging.py` | structlog configuration (JSON prod, console dev) |

### Key Design Constraints

1. **Synchronous Python** -- no asyncio. JMAPClient and CardDAVClient both use synchronous httpx.
2. **Single-threaded main loop** -- `workflow.poll()` runs sequentially; health server is the only daemon thread.
3. **Stateless** -- all state lives in Fastmail (email labels, contact groups). Service can restart at any time.
4. **Flat env vars** -- 18 individual `MAILROOM_*` env vars map directly to k8s ConfigMap entries.
5. **Startup validation** -- `resolve_mailboxes()` and `validate_groups()` crash on missing resources. Fast failure.

---

## Proposed Architecture (To-Be)

```
                    +----------------------------------------------------+
                    |                  __main__.py                        |
                    |                                                     |
                    |   main()                                            |
                    |     settings = MailroomSettings()                    |
                    |     jmap.connect()                                   |
                    |     carddav.connect()                                |
                    |     resolve_mailboxes()                              |
                    |     validate_groups()                                |
                    |     workflow = ScreenerWorkflow(...)                  |
                    |     start_health_server()                            |
                    |                                                     |
                    |     sse_listener = EventSourceListener(...)  <-- NEW |
                    |     sse_thread = Thread(target=sse_listener.run)     |
                    |     sse_thread.start()                       <-- NEW |
                    |                                                     |
                    |     while not shutdown:                              |
                    |       check sse_thread alive            <-- NEW     |
                    |       if trigger_event.wait(poll_interval):          |
                    |         # SSE triggered           <-- REPLACES SLEEP|
                    |       workflow.poll()                                |
                    +----------------------------------------------------+
                         |             |                   |
            +------------+             |                   +----------+
            |                          |                              |
   +--------v---------+    +-----------v-----------+   +--------------v------+
   |  JMAPClient       |    |  EventSourceListener  |   |  CardDAVClient       |
   |  (httpx)          |    |  (httpx-sse)     NEW  |   |  (httpx + vobject)   |
   |                   |    |                       |   |                      |
   |  connect()        |    |  run()                |   |  connect()           |
   |  call()           |    |  _connect_sse()       |   |  validate_groups()   |
   |  resolve_mailboxes|    |  _handle_event()      |   |  create_group()  NEW |
   |  query_emails()   |    |  _reconnect()         |   |  search_by_email()   |
   |  get_email_senders|    |                       |   |  create_contact()    |
   |  remove_label()   |    +-----------------------+   |  add_to_group()      |
   |  batch_move()     |              |                 |  upsert_contact()    |
   |  create_mailbox() |              |                 |  check_membership()  |
   |            NEW    |              v                 +----------------------+
   +-------------------+    Fastmail EventSource               |
            |               api.fastmail.com/jmap/event/       v
            v                                          Fastmail CardDAV API
   Fastmail JMAP API                                   carddav.fastmail.com
   api.fastmail.com
```

---

## Feature 1: JMAP EventSource Push

### Integration Point: Main Loop Replacement

The main loop in `__main__.py` currently uses `shutdown_event.wait(poll_interval)` as a fixed sleep. The change replaces this with a `threading.Event` trigger that can be set by either the SSE listener (push) or a timeout expiry (fallback poll).

**What changes in `__main__.py`:**

```python
# BEFORE (current)
while not shutdown_event.is_set():
    workflow.poll()
    shutdown_event.wait(settings.poll_interval)

# AFTER (with EventSource)
trigger = threading.Event()
sse_listener = EventSourceListener(
    token=settings.jmap_token,
    trigger=trigger,
    shutdown=shutdown_event,
    debounce_seconds=settings.debounce_seconds,
)
sse_thread = threading.Thread(target=sse_listener.run, daemon=True)
sse_thread.start()

last_poll = 0.0
while not shutdown_event.is_set():
    workflow.poll()
    last_poll = time.time()
    HealthHandler.last_successful_poll = last_poll
    trigger.clear()
    trigger.wait(timeout=settings.poll_interval)
    # Wakes on: SSE trigger, poll_interval timeout, or shutdown
```

**Why this works:** `trigger.wait(timeout=poll_interval)` blocks until either (a) the SSE listener calls `trigger.set()` on a state change, or (b) the timeout expires. Either way, `workflow.poll()` runs. The shutdown event is checked separately. This preserves the existing sequential execution model -- no concurrent polls.

### New Component: `EventSourceListener`

**File:** `src/mailroom/clients/eventsource.py` (new file in `clients/` because it is a Fastmail API client, not business logic)

**Responsibilities:**
1. Discover `eventSourceUrl` from JMAP session
2. Maintain a persistent SSE connection to Fastmail
3. Parse SSE events, filter for Email/Mailbox state changes
4. Debounce rapid events into a single trigger
5. Reconnect on disconnect with exponential backoff
6. Report health state for monitoring

**Key design decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SSE library | `httpx-sse` (v0.4.3) | Already using httpx throughout. httpx-sse provides proper SSE parsing with `iter_sse()`. The discovery script's manual line parsing works but does not handle multi-line data fields or retry directives correctly. httpx-sse is maintained (Oct 2025 release), supports sync + async, and is a single lightweight dependency. |
| Threading model | Dedicated daemon thread | The main loop is synchronous. Running SSE in a thread and signaling via `threading.Event` is the simplest integration. No asyncio needed. The health server already uses this pattern. |
| Debounce mechanism | Timer-based in the listener thread | On first event, start a debounce timer. On subsequent events, reset. When timer expires, call `trigger.set()`. All debounce state lives in the listener thread; the main thread only sees the trigger. |
| Reconnection | Exponential backoff (1s, 2s, 4s, max 60s) with jitter | Standard approach for long-lived connections. Honor SSE `retry:` field if provided. On reconnect, the initial `type: "connect"` event from Fastmail contains current state, so no gap poll is needed as long as the fallback poll covers the disconnect window. |
| httpx client | Separate from JMAP client | SSE needs different timeout settings (read=65s vs normal 30s). Pool timeout disabled. Cannot share the JMAPClient's httpx.Client instance. |
| Event filtering | `types=Email,Mailbox` query parameter | Only subscribe to Email and Mailbox state changes. ContactCard/AddressBook/Thread changes are irrelevant to triage and would cause unnecessary wakeups. |

**SSE event flow:**

```
Fastmail EventSource
    |
    v
EventSourceListener._connect_sse()
    |
    |  SSE event: {"changed": {"acct": {"Email": "J84602", "Mailbox": "J84602"}}, "type": "change"}
    |
    v
_handle_event()
    |  Filter: "Email" or "Mailbox" in changed types?
    |  Yes: reset debounce timer
    |  No: ignore (e.g., ContactCard-only)
    |
    v
Debounce timer expires (default: 3 seconds)
    |
    v
trigger.set()  -->  Main loop wakes up  -->  workflow.poll()
```

**Timeout configuration for SSE httpx client:**

```python
httpx.Client(
    timeout=httpx.Timeout(
        connect=30.0,
        read=65.0,     # 2x ping_interval (30s) + 5s buffer
        write=30.0,
        pool=None,     # No pool timeout -- SSE holds connection open
    ),
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    },
)
```

### New Config Fields

| Field | Env Var | Default | Purpose |
|-------|---------|---------|---------|
| `push_enabled` | `MAILROOM_PUSH_ENABLED` | `true` | Enable/disable EventSource. When false, service runs in poll-only mode (existing behavior). |
| `debounce_seconds` | `MAILROOM_DEBOUNCE_SECONDS` | `3` | Debounce window for SSE events before triggering poll. |
| `sse_ping_interval` | `MAILROOM_SSE_PING_INTERVAL` | `30` | Ping interval requested from Fastmail. Used to calculate read timeout. |

### Health Endpoint Changes

The `/healthz` response gains two new fields:

```json
{
    "status": "ok",
    "last_poll_age_seconds": 4.2,
    "eventsource_connected": true,
    "eventsource_thread_alive": true
}
```

These are class-level attributes on `HealthHandler`, updated by the SSE listener and checked by the main loop.

### Modified Files

| File | Change Type | What Changes |
|------|-------------|--------------|
| `__main__.py` | **Modified** | Main loop uses `trigger.wait()` instead of `shutdown_event.wait()`. Creates and monitors SSE thread. Updates HealthHandler with SSE status. |
| `core/config.py` | **Modified** | Add `push_enabled`, `debounce_seconds`, `sse_ping_interval` fields. |
| `clients/eventsource.py` | **New** | `EventSourceListener` class with SSE connection, event parsing, debounce, reconnection. |

### Dependency Change

| Package | Action | Reason |
|---------|--------|--------|
| `httpx-sse` | **Add** | SSE event parsing for httpx streaming responses. Replaces manual line parsing from discovery script. |

---

## Feature 2: Configurable Triage Categories

### Integration Point: Config Layer

The current config has 5 hardcoded label fields (`label_to_imbox`, `label_to_feed`, etc.) and 4 group fields (`group_imbox`, `group_feed`, etc.) that are stitched together in the `label_to_group_mapping` property. The change introduces a `triage_categories` field that defines categories as a list of structured objects, while keeping backward compatibility with all existing env vars.

**Current data flow (config -> workflow):**

```
MailroomSettings
    .label_to_imbox = "@ToImbox"         (flat env var)
    .group_imbox = "Imbox"               (flat env var)
        |
        v
    .label_to_group_mapping property     (stitches them together)
        {"@ToImbox": {"group": "Imbox", "destination_mailbox": "Inbox", ...}}
        |
        v
    .triage_labels property              (derived: list of label names)
    .contact_groups property             (derived: list of group names)
    .required_mailboxes property         (derived: list of all mailbox names)
        |
        v
ScreenerWorkflow._collect_triaged()      (uses triage_labels to know which mailboxes to query)
ScreenerWorkflow._process_sender()       (uses label_to_group_mapping to determine destination)
__main__.main()                          (uses required_mailboxes for startup validation)
                                         (uses contact_groups for startup validation)
```

**Proposed data flow (backward compatible):**

```
MailroomSettings
    .triage_categories = [                    (NEW: optional JSON or YAML config)
        {"label": "@ToImbox", "group": "Imbox", "destination_mailbox": "Inbox",
         "contact_type": "company", "add_inbox_label": true},
        {"label": "@ToBillboard", "group": "Billboard", ...},
    ]
    |
    +-- If triage_categories is set: use it directly
    |
    +-- If triage_categories is NOT set: build from existing flat fields
            .label_to_imbox, .group_imbox, etc. (UNCHANGED)
    |
    v
    .label_to_group_mapping property     (UNCHANGED interface, new internal logic)
    .triage_labels property              (DERIVED from mapping, not from flat fields)
    .contact_groups property             (DERIVED from mapping, not from flat fields)
    .required_mailboxes property         (DERIVED from mapping, already partially does this)
    |
    v
ScreenerWorkflow (UNCHANGED -- consumes the same properties)
__main__.main()  (UNCHANGED -- consumes the same properties)
```

**Why backward compatible:** The `ScreenerWorkflow` and `__main__` never access the flat fields directly. They consume `label_to_group_mapping`, `triage_labels`, `contact_groups`, and `required_mailboxes`. These are all computed properties. Changing how the properties are computed internally -- whether from flat fields or from a categories list -- is invisible to consumers. All 180 existing tests pass without modification.

### Category Data Model

```python
class TriageCategory(BaseModel):
    """A single triage category mapping a label to a destination."""
    label: str                          # Fastmail mailbox name, e.g. "@ToImbox"
    group: str                          # CardDAV contact group name, e.g. "Imbox"
    destination_mailbox: str            # Where swept emails go, e.g. "Inbox"
    contact_type: str = "company"       # "company" or "person"
    add_inbox_label: bool = False       # Whether to also add Inbox label (for Imbox sweep)
```

This model replaces the implicit structure in the current `label_to_group_mapping` dict. The `add_inbox_label` field replaces the hardcoded Imbox special case (`destination_mailbox == "Inbox"` check in `_get_destination_mailbox_ids`).

### Config Input Format

Two input methods, both producing the same internal list:

**Method 1: JSON env var (for k8s ConfigMap or advanced users)**

```
MAILROOM_TRIAGE_CATEGORIES='[{"label":"@ToImbox","group":"Imbox","destination_mailbox":"Inbox","contact_type":"company","add_inbox_label":true},{"label":"@ToFeed","group":"Feed","destination_mailbox":"Feed","contact_type":"company"}]'
```

**Method 2: Existing flat env vars (default, backward compatible)**

When `MAILROOM_TRIAGE_CATEGORIES` is not set, the system builds the list from the existing flat fields. This is the zero-change path for existing deployments.

**Method 3 (future): YAML config file**

Mount a ConfigMap as a file at `/config/categories.yaml`. pydantic-settings custom source reads it. This is the ergonomic path for complex configurations. Defer to v1.2 unless the JSON env var proves too painful.

### Derived Property Changes

The key change is making ALL derived properties compute from `label_to_group_mapping` rather than from individual flat fields:

```python
# BEFORE
@property
def contact_groups(self) -> list[str]:
    return [self.group_imbox, self.group_feed, self.group_paper_trail, self.group_jail]

# AFTER
@property
def contact_groups(self) -> list[str]:
    return list({entry["group"] for entry in self.label_to_group_mapping.values()})
```

This ensures that custom categories added via `triage_categories` are automatically included in startup validation.

### Modified Files

| File | Change Type | What Changes |
|------|-------------|--------------|
| `core/config.py` | **Modified** | Add `TriageCategory` model, `triage_categories` optional field, update `label_to_group_mapping` to build from categories when set, update `triage_labels`/`contact_groups`/`required_mailboxes` to derive from mapping. |
| `workflows/screener.py` | **Minimal change** | Replace hardcoded Imbox destination check with `add_inbox_label` from mapping. Everything else unchanged. |

### What Does NOT Change

- `ScreenerWorkflow.poll()` interface
- `ScreenerWorkflow._collect_triaged()` logic
- `ScreenerWorkflow._process_sender()` logic (reads from mapping, not from config fields)
- `__main__.main()` startup sequence
- All existing env vars and their defaults
- k8s ConfigMap (unless user wants custom categories)
- All 180 existing unit tests (they construct config with flat fields, which still work)

---

## Feature 3: Setup Script

### Integration Point: New Entry Point

The setup script is a standalone CLI tool that provisions Fastmail resources (mailboxes and contact groups) required by Mailroom. It is NOT part of the main service loop -- it runs once, manually, before first deployment.

**File:** `src/mailroom/setup.py` (new module) with entry in `pyproject.toml` console_scripts or invoked as `python -m mailroom.setup`.

### What It Creates

| Resource | API | Method | Notes |
|----------|-----|--------|-------|
| Triage label mailboxes (`@ToImbox`, `@ToFeed`, etc.) | JMAP | `Mailbox/set` create | Top-level mailboxes only. Check-then-create for idempotency. |
| Error/warning label mailboxes (`@MailroomError`, `@MailroomWarning`) | JMAP | `Mailbox/set` create | Same pattern. |
| Screener mailbox | JMAP | `Mailbox/set` create | If it does not already exist. |
| Destination mailboxes (`Feed`, `Paper Trail`, `Jail`) | JMAP | `Mailbox/set` create | Inbox already exists. Only create missing ones. |
| Contact groups (`Imbox`, `Feed`, `Paper Trail`, `Jail`) | CardDAV | PUT vCard with `KIND:group` | Check-then-create. Match existing `validate_groups()` format. |

### What It Cannot Create

**Fastmail sieve rules.** There is no JMAP or CardDAV API for creating email filter rules. The setup script MUST print human instructions for creating the required rules after provisioning resources. This is the most important UX concern of the setup script.

### New JMAP Method: `Mailbox/set` create

The JMAPClient needs a new method to create mailboxes:

```python
def create_mailbox(self, name: str, parent_id: str | None = None) -> str:
    """Create a top-level mailbox. Returns the new mailbox ID.

    Uses Mailbox/set with a temporary creation ID.
    Raises if the mailbox already exists at the same parent level.
    """
    responses = self.call([
        ["Mailbox/set", {
            "accountId": self.account_id,
            "create": {
                "new-mailbox": {
                    "name": name,
                    "parentId": parent_id,
                }
            }
        }, "mc0"]
    ])
    data = responses[0][1]
    created = data.get("created", {})
    if "new-mailbox" in created:
        return created["new-mailbox"]["id"]
    not_created = data.get("notCreated", {})
    raise RuntimeError(f"Failed to create mailbox '{name}': {not_created}")
```

### New CardDAV Method: Group Creation

The CardDAVClient needs a method to create contact groups:

```python
def create_group(self, group_name: str) -> dict:
    """Create an Apple-style contact group vCard.

    Returns dict with 'href', 'etag', 'uid'.
    """
    group_uid = str(uuid.uuid4())
    card = vobject.vCard()
    card.add("uid").value = group_uid
    card.add("fn").value = group_name
    card.add("x-addressbookserver-kind").value = "group"

    href_path = f"{group_uid}.vcf"
    put_url = f"{self._addressbook_url}{href_path}"

    resp = self._http.put(
        put_url,
        content=card.serialize().encode("utf-8"),
        headers={
            "Content-Type": "text/vcard; charset=utf-8",
            "If-None-Match": "*",
        },
    )
    resp.raise_for_status()
    return {"href": f"/{group_uid}.vcf", "etag": resp.headers.get("etag", ""), "uid": group_uid}
```

### Setup Script Flow

```
1. Load settings (same MailroomSettings as main service)
2. Connect JMAP + CardDAV (same connect() calls)
3. Print: "Configuring Fastmail account: {carddav_username} (JMAP account: {account_id})"
4. Confirm or --yes flag to proceed
5. For each required mailbox:
   a. Check if exists (Mailbox/get, match by name)
   b. If exists: print "  [exists] @ToImbox"
   c. If missing: create via Mailbox/set, print "  [created] @ToImbox"
6. For each required contact group:
   a. Check if exists (fetch all groups, match by FN)
   b. If exists: print "  [exists] Imbox"
   c. If missing: create via PUT vCard, print "  [created] Imbox"
7. Print sieve rule instructions (human-readable, copy-pasteable)
8. Print post-setup checklist
```

### Sieve Rule Output

The setup script prints instructions like:

```
========================================
MANUAL STEP: Create Fastmail Filter Rules
========================================

You must create these rules in Fastmail Settings > Filters & Rules.
Without them, future emails will not be auto-routed after triage.

Rule 1: Route Imbox contacts to Inbox
  Condition: Sender is in contact group "Imbox"
  Action: Move to Inbox

Rule 2: Route Feed contacts to Feed
  Condition: Sender is in contact group "Feed"
  Action: Move to Feed mailbox

Rule 3: Route Paper Trail contacts to Paper Trail
  Condition: Sender is in contact group "Paper Trail"
  Action: Move to Paper Trail mailbox

Rule 4: Route Jail contacts to Jail
  Condition: Sender is in contact group "Jail"
  Action: Move to Jail mailbox, Mark as Read

Rule 5: Gate unknown senders
  Condition: Sender is NOT in any of the above groups
  Action: Move to Screener mailbox

IMPORTANT: Rules are evaluated top to bottom. Place Rule 5 LAST.
========================================
```

If configurable categories are set, the instructions dynamically include the custom categories.

### Modified Files

| File | Change Type | What Changes |
|------|-------------|--------------|
| `setup.py` | **New** | Setup script module with `main()` entry point. |
| `clients/jmap.py` | **Modified** | Add `create_mailbox()` method. |
| `clients/carddav.py` | **Modified** | Add `create_group()` method. |
| `pyproject.toml` | **Modified** | Add `[project.scripts]` entry for `mailroom-setup = "mailroom.setup:main"` or document `python -m mailroom.setup` usage. |

---

## Component Boundary Summary

### New Components

| Component | File | Responsibility | Communicates With |
|-----------|------|----------------|-------------------|
| **EventSourceListener** | `clients/eventsource.py` | SSE connection, event filtering, debounce, reconnection | Fastmail EventSource API, main loop (via threading.Event) |
| **TriageCategory** | `core/config.py` (inner model) | Data model for one category mapping | MailroomSettings (parent model) |
| **Setup Script** | `setup.py` | One-time provisioning of Fastmail resources | JMAPClient, CardDAVClient, MailroomSettings |

### Modified Components

| Component | File | What Changes |
|-----------|------|--------------|
| **Main Loop** | `__main__.py` | SSE thread lifecycle, trigger-based wakeup, thread health monitoring, expanded health endpoint |
| **Config** | `core/config.py` | `triage_categories` field, backward-compatible property derivation, new push config fields |
| **JMAPClient** | `clients/jmap.py` | `create_mailbox()` method (setup script only), `eventSourceUrl` discovery from session |
| **CardDAVClient** | `clients/carddav.py` | `create_group()` method (setup script only) |
| **ScreenerWorkflow** | `workflows/screener.py` | Replace hardcoded Imbox check with `add_inbox_label` from mapping (minor) |
| **HealthHandler** | `__main__.py` | Two new fields: `eventsource_connected`, `eventsource_thread_alive` |

### Unchanged Components

| Component | File | Why Unchanged |
|-----------|------|---------------|
| **Logging** | `core/logging.py` | No changes needed. New components use existing `structlog.get_logger()`. |
| **ScreenerWorkflow.poll()** | `workflows/screener.py` | The poll method's interface and internal logic are unchanged. It still processes triaged emails the same way. The only change is WHO calls it (trigger vs sleep) and WHERE the mapping comes from (categories vs flat fields), both of which are external to this method. |

---

## Data Flow: Push-Triggered Triage

```
User applies @ToFeed label to email in Fastmail
    |
    v
Fastmail sends SSE event: {"changed": {"acct": {"Email": "J84603", "Mailbox": "J84603"}}, "type": "change"}
    |
    v
EventSourceListener receives event via httpx-sse iter_sse()
    |
    v
_handle_event() filters: "Email" in changed types? Yes.
    |
    v
Debounce timer starts (3s). No more events arrive.
    |
    v
Timer expires -> trigger.set()
    |
    v
Main loop: trigger.wait(300) returns early
    |
    v
workflow.poll()
    |-- _collect_triaged() queries @ToFeed mailbox, finds email
    |-- _process_sender() looks up mapping: @ToFeed -> {group: "Feed", destination: "Feed"}
    |-- carddav.upsert_contact() adds sender to Feed group
    |-- jmap.batch_move_emails() sweeps Screener -> Feed
    |-- jmap.remove_label() removes @ToFeed from triggering email
    |
    v
trigger.clear() -> back to waiting
```

Total latency: SSE propagation (~1s) + debounce (3s) + poll execution (~2-5s) = **~6-9 seconds** vs current **up to 5 minutes**.

---

## Data Flow: Configurable Category

```
User sets MAILROOM_TRIAGE_CATEGORIES with extra category:
    [...existing 5..., {"label": "@ToBillboard", "group": "Billboard",
     "destination_mailbox": "Paper Trail", "contact_type": "company"}]
    |
    v
MailroomSettings.__init__() parses JSON into list[TriageCategory]
    |
    v
label_to_group_mapping now includes:
    "@ToBillboard": {"group": "Billboard", "destination_mailbox": "Paper Trail", ...}
    |
    v
triage_labels includes "@ToBillboard"
contact_groups includes "Billboard"
required_mailboxes includes "@ToBillboard" and "Paper Trail" (already present)
    |
    v
Startup validation: resolve_mailboxes() checks @ToBillboard exists
                     validate_groups() checks Billboard group exists
    |
    v
Service runs. When user applies @ToBillboard:
    _collect_triaged() queries @ToBillboard mailbox
    _process_sender() maps to Billboard group, Paper Trail destination
    Everything else is identical to existing labels.
```

---

## Suggested Build Order

Based on component dependencies and integration risk:

### Phase 1: Configurable Categories

**Build first because:** The config layer is the foundation. EventSource and setup script both need to know what categories exist. Building categories first means the setup script can provision dynamic categories, and EventSource benefits from a clean config model.

**Changes:**
1. Add `TriageCategory` model to `core/config.py`
2. Add optional `triage_categories` field
3. Update `label_to_group_mapping` to build from categories when set
4. Update `triage_labels`, `contact_groups`, `required_mailboxes` to derive from mapping
5. Replace Imbox hardcoded check in `_get_destination_mailbox_ids` with `add_inbox_label`
6. Tests: config backward compat, custom category inclusion in derived properties, Imbox label behavior

**Risk:** LOW. Internal refactor of config properties. No new external dependencies. All existing tests should pass without modification (the litmus test for backward compatibility).

### Phase 2: Setup Script

**Build second because:** It needs the config layer (to know what to provision) and it exercises `Mailbox/set` create and CardDAV group creation -- operations that should be validated before the main service depends on them.

**Changes:**
1. Add `create_mailbox()` to `JMAPClient`
2. Add `create_group()` to `CardDAVClient`
3. Create `setup.py` with idempotent provisioning logic
4. Add console script entry point
5. Human test: run setup twice, verify idempotency

**Risk:** MEDIUM. `Mailbox/set` create is a new JMAP operation not previously used. Idempotency with Fastmail's mailbox name uniqueness needs live testing. CardDAV group creation is straightforward (same pattern as `create_contact` but with `KIND:group`).

### Phase 3: EventSource Push

**Build last because:** It is the highest-complexity feature with the most new code, a new dependency, and a new threading model. The config and setup script are prerequisites (push-enabled flag, categories for event filtering). Building push last means the service is fully functional with polling before push is added, providing a clean fallback.

**Changes:**
1. Add `httpx-sse` dependency
2. Create `clients/eventsource.py` with `EventSourceListener`
3. Modify `__main__.py` main loop for trigger-based wakeup
4. Add SSE thread lifecycle management
5. Expand health endpoint with SSE status
6. Add push config fields (`push_enabled`, `debounce_seconds`, `sse_ping_interval`)
7. Tests: debounce logic, event filtering, reconnection, thread health
8. Human test: verify SSE triggers triage within seconds

**Risk:** MEDIUM-HIGH. Long-lived SSE connections have known failure modes (silent death, proxy buffering, TCP half-open). The threading model adds complexity. However, the polling fallback means push failures degrade gracefully to existing behavior rather than causing outages.

### Build Order Rationale

```
Phase 1: Configurable Categories (config refactor)
    |
    +-- No new dependencies
    +-- No new threads
    +-- Internal refactor only
    +-- All existing tests pass (backward compat gate)
    |
    v
Phase 2: Setup Script (new entry point + JMAP/CardDAV methods)
    |
    +-- Depends on: categories config (to know what to provision)
    +-- Validates: Mailbox/set create (new JMAP operation)
    +-- Validates: CardDAV group creation (new CardDAV operation)
    +-- Standalone tool, does not affect running service
    |
    v
Phase 3: EventSource Push (new component + threading)
    |
    +-- Depends on: push config fields from Phase 1
    +-- Highest complexity (SSE, threading, debounce)
    +-- Graceful degradation (polling fallback)
    +-- Service fully functional before this phase
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Making EventSource the Only Trigger

**What:** Remove polling entirely and rely solely on SSE for triggering triage.
**Why bad:** SSE connections fail silently (proxy buffering, TCP half-open, server timeouts). Without polling fallback, a dead SSE connection means zero triage until someone notices. Fastmail's own blog acknowledges SSE connections die on sleep/wake and require manual reconnection.
**Instead:** Keep polling as a safety net. EventSource is an optimization (low latency), not a replacement (reliability).

### Anti-Pattern 2: Breaking Config Backward Compatibility

**What:** Remove the flat env vars and force everyone to use `MAILROOM_TRIAGE_CATEGORIES` JSON.
**Why bad:** Breaks 180 tests, breaks existing k8s ConfigMap, breaks existing deployment, creates migration friction for a single-user tool.
**Instead:** Both paths work. Flat vars for existing deployments, categories JSON for custom setups. Flat vars are the default.

### Anti-Pattern 3: Async SSE Listener

**What:** Use `asyncio` for the SSE listener because "SSE is naturally async."
**Why bad:** The rest of the codebase is synchronous. Mixing async and sync requires `asyncio.run_in_executor()` or a separate event loop in a thread. `workflow.poll()` is synchronous. The main loop is synchronous. Adding asyncio for one component creates accidental complexity.
**Instead:** Use synchronous httpx-sse in a dedicated thread. The thread blocks on `iter_sse()`, which is exactly what a background listener should do. No event loop needed.

### Anti-Pattern 4: Setup Script That Runs Automatically on Service Start

**What:** Have the main service auto-provision missing resources at startup instead of a separate setup script.
**Why bad:** The current startup validation (crash on missing mailboxes/groups) is a deliberate safety net. If the service silently creates missing resources, a typo in config (`@ToImobx` instead of `@ToImbox`) creates a junk mailbox instead of failing fast. Auto-provisioning also means every pod restart potentially creates resources, making debugging harder.
**Instead:** Separate setup script, run manually once. Main service validates and crashes on missing resources. This separation keeps the failure-fast safety net.

---

## Sources

- [RFC 8620 Section 7.3: Event Source](https://www.rfc-editor.org/rfc/rfc8620#section-7.3) -- JMAP EventSource specification (HIGH confidence)
- [RFC 8621: JMAP for Mail](https://www.rfc-editor.org/rfc/rfc8621.html) -- Mailbox/set create, name uniqueness constraints (HIGH confidence)
- [Fastmail blog: EventSource/SSE](https://www.fastmail.com/blog/building-the-new-ajax-mail-ui-part-1-instant-notifications-of-new-emails-via-eventsourceserver-sent-events/) -- Connection timeout behavior, reconnection gotchas (MEDIUM confidence)
- [Fastmail JMAP-Samples #7](https://github.com/fastmail/JMAP-Samples/issues/7) -- Third-party EventSource auth, personal API tokens required, spec deviations (HIGH confidence)
- [httpx-sse v0.4.3 PyPI](https://pypi.org/project/httpx-sse/) -- SSE client library for httpx, sync + async support, Python 3.9-3.13 (HIGH confidence)
- [pydantic-settings: Complex Types](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- JSON env var parsing, nested delimiter, complex types in env vars (HIGH confidence)
- Mailroom codebase: `src/mailroom/` -- all source files directly inspected (HIGH confidence)
- Mailroom EventSource research: `.research/jmap-eventsource/jmap-eventsource.md` -- Fastmail SSE format, event envelope, observed types (HIGH confidence)
- Discovery script: `.research/jmap-eventsource/eventsource_discovery.py` -- empirical SSE connection behavior (HIGH confidence)

---
*Architecture research for: v1.1 Push, Configurable Categories, and Setup Script*
*Researched: 2026-02-25*
