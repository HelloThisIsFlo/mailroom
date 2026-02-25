# Feature Landscape: v1.1 Push & Config

**Domain:** Email triage automation -- JMAP EventSource push, configurable categories, setup automation
**Researched:** 2026-02-25
**Overall confidence:** HIGH (existing codebase verified, RFC specs consulted, Fastmail behavior observed via discovery script)

## Context

v1.0 is shipped and running. This research covers ONLY the three new features for v1.1:

1. **JMAP EventSource push notifications** -- replace polling with SSE-triggered triage
2. **Configurable triage categories** -- user-defined label/group/inbox mappings
3. **Fastmail setup script** -- auto-provision required labels and contact groups

Existing v1.0 features (polling, triage pipeline, conflict detection, contact upsert, sweep, etc.) are already built and tested with 180 unit tests + 13 human integration tests.

---

## Table Stakes

Features that MUST ship for v1.1 to deliver on its promise. Missing any of these means the milestone is incomplete.

### 1. EventSource SSE Connection

| Aspect | Detail |
|--------|--------|
| **Why expected** | Core promise of v1.1 is replacing polling with push. Without a working SSE connection, there is no push. |
| **Complexity** | LOW -- httpx streaming with manual line parsing (no new dependencies needed) |
| **Dependencies** | Existing `JMAPClient.connect()` already fetches session; just store `eventSourceUrl` |
| **What it does** | Connect to Fastmail's EventSource endpoint, subscribe to `Email,Mailbox` types, receive state change events in real time |
| **Protocol** | RFC 8620 Section 7.3 -- `GET {eventSourceUrl}?types=Email,Mailbox&closeafter=no&ping=30` with Bearer auth and `Accept: text/event-stream` |
| **Fastmail behavior** | Wraps RFC data in `{"changed": {...}, "type": "connect|change"}` envelope. Initial connect sends current state for Email, Mailbox, Thread, ContactCard, AddressBook, EmailDelivery. Subsequent events fire on state changes. (Verified via discovery script) |
| **Key decision** | Manual SSE parsing, not a third-party library. SSE format is simple (event/data/comment line prefixes, empty-line delimiters). httpx streaming handles it natively. |

**Confidence:** HIGH -- verified against live Fastmail via `human-tests/test_14_eventsource.py` discovery script. Event format documented in `.research/jmap-eventsource/jmap-eventsource.md`.

### 2. Debounced Triage Triggering

| Aspect | Detail |
|--------|--------|
| **Why expected** | Raw SSE events fire on every state change. Without debouncing, batch email arrivals trigger N redundant triage passes. |
| **Complexity** | LOW -- queue + timer pattern, standard concurrency |
| **Dependencies** | EventSource connection (Feature 1) |
| **What it does** | Accumulate SSE events over a short window (default 3s), then trigger a single `workflow.poll()`. Multiple events during the debounce window collapse into one triage pass. |
| **Behavior matrix** | Email arrives: SSE fires ~1s, debounce 3s, poll runs. 5 emails arrive rapidly: debounce collapses to single poll. SSE drops: fallback to polling. Nothing happens for 5 min: fallback poll runs. |
| **Key decision** | Debounce window configurable via `MAILROOM_DEBOUNCE_SECONDS` (default 3). Not too short (rapid events still cause multiple polls) and not too long (latency defeats the purpose of push). |

**Confidence:** HIGH -- debounce pattern is well-understood. Integration sketch in `.research/jmap-eventsource/integration-sketch.md` shows exact code structure.

### 3. Polling Fallback

| Aspect | Detail |
|--------|--------|
| **Why expected** | SSE connections drop. Network issues happen. Without fallback, the service stops processing entirely when SSE disconnects. |
| **Complexity** | LOW -- the existing polling loop is the fallback; the new code wraps it |
| **Dependencies** | Existing `workflow.poll()` (unchanged) |
| **What it does** | If no SSE event arrives within `poll_interval` (300s), run a poll anyway. If SSE disconnects and cannot reconnect, service degrades to pure polling (same as v1.0). |
| **Reconnection strategy** | Immediate reconnect on clean disconnect, exponential backoff (1s, 2s, 4s, max 60s) on errors, honor `retry:` field from server. After reconnecting, one full poll to catch missed events. |
| **Key decision** | Hybrid push+poll is the correct architecture. EventSource is the primary trigger; polling is the safety net. This is standard practice in JMAP client implementations. |

**Confidence:** HIGH -- the existing polling loop already works; fallback just keeps it as a backstop.

### 4. Configurable Triage Category Mapping

| Aspect | Detail |
|--------|--------|
| **Why expected** | v1.0 hardcodes 5 triage labels and 4 contact groups. Users cannot add categories like "Billboard", "Truck", "Bank" without changing code. Configurable mappings let users define their own triage taxonomy. |
| **Complexity** | MEDIUM -- config model change, validation logic, backward compatibility |
| **Dependencies** | Existing `MailroomSettings`, `ScreenerWorkflow`, startup validation |
| **What it does** | Replace 18 individual env vars for labels/groups with a structured triage mapping. Each entry defines: triage label (e.g. `@ToBillboard`), contact group (e.g. `Billboard`), destination mailbox (e.g. `Paper Trail`), and contact type (company/person). |
| **Config format** | JSON-encoded env var `MAILROOM_TRIAGE_MAP` containing a list of mapping objects. pydantic-settings parses complex types (list, dict, BaseModel) from JSON-encoded env var values automatically. |
| **Backward compatibility** | Default value matches current v1.0 categories exactly. Existing ConfigMaps continue to work without changes. |

**Confidence:** HIGH -- pydantic-settings JSON parsing for complex types is documented and reliable. The existing `label_to_group_mapping` property already returns the exact data structure this replaces.

### 5. Setup Script: Mailbox/Label Provisioning

| Aspect | Detail |
|--------|--------|
| **Why expected** | v1.0 crashes at startup if required labels or groups are missing, with a message telling users to create them manually in Fastmail. The setup script eliminates this manual step. |
| **Complexity** | MEDIUM -- JMAP `Mailbox/set` for creating mailboxes, idempotency checks |
| **Dependencies** | Configurable triage mapping (Feature 4) -- reads the config to know what to create |
| **What it does** | Read the triage mapping config, check what already exists on Fastmail via `Mailbox/get`, create missing mailboxes via `Mailbox/set`. Report what was created vs. skipped. |
| **JMAP method** | `Mailbox/set` with `create` property. Required fields: `name` (string). Optional: `parentId` (null for top-level), `sortOrder`, `isSubscribed`. RFC 8621 Section 2. |
| **Idempotency** | Fetch all mailboxes first, create only what is missing. If a mailbox already exists with the same name, skip it. Matches by name (case-sensitive, matching Fastmail behavior). |

**Confidence:** HIGH -- `Mailbox/set` is a standard JMAP method per RFC 8621. The existing `JMAPClient.resolve_mailboxes()` already fetches all mailboxes, so the "check what exists" part is trivially reusable.

### 6. Setup Script: Contact Group Provisioning

| Aspect | Detail |
|--------|--------|
| **Why expected** | Same as mailbox provisioning -- v1.0 requires groups to exist manually. |
| **Complexity** | MEDIUM -- CardDAV group creation via vCard PUT |
| **Dependencies** | Configurable triage mapping (Feature 4), existing `CardDAVClient` |
| **What it does** | Read unique contact groups from config, check which exist via `validate_groups()` (catch ValueError instead of crashing), create missing groups as Apple-style group vCards. |
| **CardDAV method** | PUT a new vCard with `X-ADDRESSBOOKSERVER-KIND:group` and `FN:{group name}` to the addressbook. Same format Fastmail uses natively. Generate a UUID, PUT to `{addressbook_url}/{uuid}.vcf` with `If-None-Match: *`. |
| **Idempotency** | Fetch all group vCards first (existing `validate_groups()` logic), create only missing ones. If group already exists, skip it. |

**Confidence:** HIGH -- the existing `CardDAVClient.create_contact()` already does vCard PUT to the same addressbook. Group creation uses the same mechanism with different vCard content (KIND:group instead of individual contact).

---

## Differentiators

Features that add meaningful value beyond the minimum. Worth building in v1.1 if time allows, but the milestone ships without them.

### Configurable Debounce Escalation

| Aspect | Detail |
|--------|--------|
| **Value** | If SSE disconnects for >60s, temporarily increase poll frequency to 30s instead of waiting the full 5 min. Faster recovery from SSE outages. |
| **Complexity** | LOW -- timer check in the polling loop |
| **Depends on** | EventSource connection + polling fallback |

### Setup Script Dry-Run Mode

| Aspect | Detail |
|--------|--------|
| **Value** | Show what the setup script WOULD create without actually making changes. Builds confidence before modifying a production Fastmail account. |
| **Complexity** | LOW -- same check logic, skip the write calls, print the plan |
| **Depends on** | Setup script (Features 5 + 6) |

### Setup Script: Fastmail Sieve Rule Validation

| Aspect | Detail |
|--------|--------|
| **Value** | After creating labels and groups, verify that Fastmail sieve rules exist to route emails from each contact group to the correct destination mailbox. The setup script cannot CREATE sieve rules (no API), but it could warn if routing rules appear missing. |
| **Complexity** | HIGH -- Fastmail sieve rules are not accessible via standard JMAP. Would need to detect routing gaps indirectly (e.g., check if emails in a group's destination mailbox actually have the right label). |
| **Depends on** | Setup script, deep Fastmail knowledge |
| **Recommendation** | SKIP for v1.1. Sieve rules are a one-time manual setup. Document the required rules in the README instead. |

### EventSource Connection Health in /healthz

| Aspect | Detail |
|--------|--------|
| **Value** | Expose SSE connection status in the health endpoint (connected/disconnected/reconnecting). Lets k8s monitoring distinguish between "service is healthy but SSE is down" vs "service is fully operational". |
| **Complexity** | LOW -- add a field to the health JSON response |
| **Depends on** | EventSource connection, existing health endpoint |

### Migration Guide for Existing Users

| Aspect | Detail |
|--------|--------|
| **Value** | Document how to migrate from v1.0's per-env-var config to v1.1's structured triage mapping. Show the old ConfigMap and the equivalent new one. |
| **Complexity** | LOW -- documentation only |
| **Depends on** | Configurable triage mapping (Feature 4) |

---

## Anti-Features

Features to explicitly NOT build in v1.1.

| Anti-Feature | Why Tempting | Why Avoid | What to Do Instead |
|--------------|-------------|-----------|-------------------|
| WebSocket push instead of SSE | "WebSockets are bidirectional and more robust" | JMAP spec mandates EventSource (SSE), not WebSockets. Fastmail only supports SSE. Building WebSocket would mean proxying SSE through a WebSocket layer for zero benefit. | Use SSE as specified by RFC 8620 Section 7.3. |
| IMAP IDLE as fallback | "IMAP IDLE is another push mechanism" | Already explicitly out of scope. Adds a second protocol (IMAP) alongside JMAP. EventSource + polling fallback provides sufficient reliability. | Hybrid SSE + polling is the correct approach. |
| Full config file (YAML/TOML) replacing env vars | "A YAML config file is more natural for structured data" | Breaks k8s ConfigMap workflow. Current deployment uses `envFrom` to inject all vars. A config file would need a mounted volume or embedded ConfigMap data. JSON-encoded env var for the triage map is the right balance: structured data, k8s-compatible. | Use `MAILROOM_TRIAGE_MAP` as a JSON-encoded env var. Keep all other settings as individual env vars. |
| Sieve rule auto-generation | "The setup script should create routing rules too" | Fastmail does not expose sieve rules via JMAP or any public API. The only way is through the Fastmail web UI. Attempting to reverse-engineer their sieve API would be fragile and unsupported. | Document the required sieve rules in the README. Users set them up once. |
| Per-event-type processing | "Parse each SSE event to determine exactly what changed, then run only relevant triage steps" | Over-engineering. The triage pipeline (`workflow.poll()`) is fast and idempotent. Running it on any state change is cheap. Parsing event types to micro-optimize which steps to run adds complexity for negligible performance gain. | Treat SSE events as a simple "something changed" signal. Run the full triage pipeline on every signal. |
| Async/await rewrite | "SSE listener should be async for efficiency" | The service is I/O-bound on external API calls, not CPU-bound. Threading (one SSE listener thread, one main thread for polling) is simpler, debuggable, and sufficient. Async adds complexity (event loops, async httpx, asyncio.Queue) for zero measurable benefit in a single-user service. | Use threads. SSE listener pushes to `queue.Queue`, main thread reads from it. |
| Auto-removal of old categories | "If user removes a category from config, auto-delete the label and group from Fastmail" | Destructive operation. Deleting a mailbox could lose emails. Removing a contact group could orphan contacts from routing rules. | Log a warning if Fastmail has labels/groups not in the config. Let the user clean up manually. |

---

## Feature Dependencies

```
[Configurable Triage Mapping] (Feature 4)
    |
    +---> [Setup Script: Mailbox Provisioning] (Feature 5)
    |         |
    |         +---> reads config to know what labels to create
    |
    +---> [Setup Script: Group Provisioning] (Feature 6)
    |         |
    |         +---> reads config to know what groups to create
    |
    +---> [ScreenerWorkflow] (existing, unchanged logic)
              |
              +---> uses config mapping instead of hardcoded properties

[EventSource SSE Connection] (Feature 1)
    |
    +---> [Debounced Triage Triggering] (Feature 2)
    |         |
    |         +---> collapses rapid events into single poll()
    |
    +---> [Polling Fallback] (Feature 3)
              |
              +---> ensures reliability when SSE is down

[Setup Script] (Features 5 + 6)
    |
    +---> INDEPENDENT from EventSource (Features 1-3)
    |     (can be built and shipped separately)
    |
    +---> DEPENDENT on Config (Feature 4)
          (must know the categories to provision)
```

### Critical Ordering Constraints

1. **Config before Setup Script** -- the setup script reads the triage mapping to know what to create. Config model must be finalized first.
2. **Config before EventSource** -- no hard dependency, but config should settle before adding push complexity. Simpler to test EventSource against a stable config model.
3. **SSE Connection before Debounce** -- debounce has nothing to debounce without events.
4. **Setup Script is independent of push** -- can be built in parallel with EventSource work.

---

## Impact on Existing Code

| File | EventSource Impact | Config Impact | Setup Script Impact |
|------|-------------------|---------------|---------------------|
| `clients/jmap.py` | +5 lines: store + expose `eventSourceUrl` from session | None | +1 method: `create_mailbox(name, parent_id=None)` wrapping `Mailbox/set` |
| `clients/carddav.py` | None | None | +1 method: `create_group(name)` wrapping vCard PUT with KIND:group |
| `core/config.py` | +1 field: `debounce_seconds: int = 3` | Major: replace 9 individual label/group fields with `triage_map` list; preserve derived properties for backward compat | None (config is consumed, not modified) |
| `workflows/screener.py` | None (poll() is unchanged) | Possible: verify it reads from config properties correctly after refactor | None |
| `__main__.py` | Major: SSE listener thread, debounce loop, fallback logic (~50 new lines) | Minor: pass new config fields | None (setup script is separate entry point) |
| NEW: `scripts/setup.py` or `__main__.py --setup` | None | Reads triage mapping | This IS the setup script |
| NEW: human tests | test_15_eventsource_push.py | test_16_custom_categories.py (if needed) | test_17_setup_script.py |

### What Does NOT Change

- `ScreenerWorkflow.poll()` -- untouched, still the same pure triage cycle
- `CardDAVClient` core operations (search, create_contact, upsert_contact, add_to_group)
- Health endpoint fundamentals (may gain SSE status field)
- Graceful shutdown pattern (same SIGTERM/SIGINT, SSE thread is daemon)
- Human integration tests 1-13 (they call workflow.poll() directly)

---

## MVP Recommendation for v1.1

### Must Ship (defines the milestone)

1. **Configurable triage mapping** -- unblocks both setup script and future category additions
2. **EventSource SSE with debounce and polling fallback** -- the headline feature
3. **Setup script for labels and groups** -- eliminates the #1 onboarding friction point

### Ship If Time Allows

4. **SSE health status in /healthz** -- trivial and useful for operations
5. **Setup script dry-run mode** -- builds confidence, small effort
6. **Migration docs** -- helps existing deployment transition

### Defer to v1.2+

- Debounce escalation on SSE disconnect (nice but not essential)
- Sieve rule validation (too complex, not API-accessible)
- Per-event-type processing (premature optimization)

---

## Complexity Summary

| Feature | Lines of New Code (est.) | New Dependencies | Risk |
|---------|--------------------------|------------------|------|
| EventSource SSE connection | ~40 | None (httpx streaming) | LOW -- protocol verified via discovery script |
| Debounce logic | ~30 | None (stdlib queue + threading) | LOW -- standard pattern |
| Polling fallback | ~20 | None | LOW -- existing code wrapped |
| Configurable triage mapping | ~60 | None | MEDIUM -- config model change touches derived properties |
| Setup script: mailboxes | ~40 | None | LOW -- standard JMAP Mailbox/set |
| Setup script: groups | ~40 | None | LOW -- same PUT pattern as contact creation |
| **Total** | **~230** | **None** | **Overall: LOW-MEDIUM** |

The entire v1.1 milestone adds approximately 230 lines of production code with zero new dependencies. The highest-risk item is the config model change because it affects derived properties used throughout the codebase.

---

## Sources

- [RFC 8620 Section 7.3: Event Source](https://www.rfc-editor.org/rfc/rfc8620) -- JMAP EventSource specification (HIGH confidence)
- [RFC 8621: JMAP for Mail](https://www.rfc-editor.org/rfc/rfc8621.html) -- Mailbox/set create properties (HIGH confidence)
- [Pydantic Settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- JSON parsing for complex env var types (HIGH confidence)
- [Fastmail API Documentation](https://www.fastmail.com/dev/) -- JMAP endpoint discovery (HIGH confidence)
- [JMAP Crash Course](https://jmap.io/crash-course.html) -- JMAP request structure reference
- [CardDAV Group Implementation](https://github.com/mstilkerich/rcmcarddav/blob/master/doc/GROUPS.md) -- X-ADDRESSBOOKSERVER-KIND group vCard format (HIGH confidence)
- `.research/jmap-eventsource/jmap-eventsource.md` -- Project-specific EventSource research with live Fastmail observations (HIGH confidence)
- `.research/jmap-eventsource/integration-sketch.md` -- Detailed code-level integration plan (HIGH confidence)
- Existing codebase: `src/mailroom/core/config.py`, `src/mailroom/clients/jmap.py`, `src/mailroom/clients/carddav.py`, `src/mailroom/__main__.py` -- current implementation (HIGH confidence)

---
*Feature research for: v1.1 Push & Config milestone*
*Researched: 2026-02-25*
