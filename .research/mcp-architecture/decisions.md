# MCP Design Decisions & Tradeoffs

> **Related files**: [README.md](README.md) (architecture overview) | [index.html](index.html) (interactive visual)

Each decision below captures the choice made, alternatives considered, and the reasoning.

---

## DEC-01: Monorepo (single package)

**Decision**: The MCP server lives in `src/mailroom/mcp/` inside the existing package.

**Alternatives considered**:
- **Separate repo + package** (`mailroom-mcp`): Would require publishing `mailroom` as a library or path-hacking imports. Two repos, two CI pipelines, version coordination.
- **Monorepo, separate package** (workspace): Python workspaces are less mature than JS. Adds `pyproject.toml` complexity for a team of one.

**Why this wins**:
- The MCP server's primary value is importing `mailroom.clients.jmap` and `mailroom.core.config` directly. Splitting breaks that or adds overhead.
- One venv, one `uv.lock`, one test suite, one CI pipeline.
- The project is small (~950 lines of source). A `mcp/` subdirectory is proportionate.
- The `mailroom-mcp` entry point in `pyproject.toml` gives a clean invocation boundary.

**Risk**: The `mcp` dependency (~FastMCP + its transitive deps) gets pulled into the polling service's Docker image. Mitigated by the fact that FastMCP is lightweight and the image already includes `httpx`, `structlog`, `pydantic` which FastMCP also depends on.

---

## DEC-02: No config split

**Decision**: The MCP server reads the same `config.yaml` and `MAILROOM_*` environment variables as the polling service.

**Alternatives considered**:
- **Separate MCP config file**: Duplicates credentials, diverges over time.
- **MCP-specific config section** in `config.yaml`: Premature — there's nothing MCP-specific to configure yet.

**Why this wins**:
- Zero new config surface. If you can run `mailroom run`, you can run `mailroom mcp`.
- The JMAP token is the same. The category definitions are the same. The mailbox names are the same.
- If MCP-specific settings emerge later (e.g., tool allowlists), they can be added as a new `mcp:` section in `config.yaml` without breaking anything.

---

## DEC-03: No workflow dependency from MCP

**Decision**: `mcp/tools.py` imports from `mailroom.clients` and `mailroom.core`, never from `mailroom.workflows`.

**Alternatives considered**:
- **Expose `ScreenerWorkflow.poll()` as an MCP tool**: Dangerous — automated triage triggered by a casual Claude conversation could move hundreds of emails. The workflow has side effects (label removal, contact creation) that are appropriate for automation but not interactive use.
- **Share helper methods** from `ScreenerWorkflow`: Couples the MCP server to automation internals. If the workflow changes (e.g., new conflict detection logic), MCP tools shouldn't need updating.

**Why this wins**:
- Clean separation of concerns: the workflow embodies *policy* (conflict detection, retry safety, triage label ordering). MCP tools are *operations* (read this, move that).
- Interactive tools are deliberately scoped — `move_email` moves one email where you tell it. `poll()` sweeps all triage labels and makes autonomous decisions.
- The client layer (`JMAPClient`) is the right abstraction boundary for MCP tools. It provides email operations without triage opinions.

---

## DEC-04: Sync client in async tools

**Decision**: MCP tool functions are `async def` (FastMCP convention) but call `JMAPClient` methods synchronously (they use `httpx.Client`, not `httpx.AsyncClient`).

**Alternatives considered**:
- **Rewrite JMAPClient to use `httpx.AsyncClient`**: Massive refactor. Infects `ScreenerWorkflow`, `__main__.py`, all tests. No benefit for the polling service.
- **Wrap sync calls in `asyncio.to_thread()`**: Technically cleaner for async purity but adds complexity. Since MCP stdio transport processes one request at a time, there's no concurrent request handling to worry about.

**Why this wins**:
- Zero changes to existing code. The MCP server adapts to the client, not the other way around.
- stdio MCP transport is inherently serial — there's no event loop contention from blocking sync calls.
- `httpx.Client` is thread-safe and well-behaved for short-lived HTTP calls. Each JMAP round-trip completes in ~100ms.

**When to revisit**: If the MCP server ever moves to SSE/HTTP transport with concurrent requests, wrapping sync calls in `to_thread()` becomes worthwhile. Or if the project migrates to async clients for other reasons.

---

## DEC-05: stdio transport

**Decision**: The MCP server uses stdio transport (FastMCP default). Claude Desktop/Code launches it as a subprocess.

**Alternatives considered**:
- **SSE (Server-Sent Events) transport**: Enables remote access and multiple concurrent clients. Requires a persistent HTTP server process, port management, and authentication.
- **Streamable HTTP**: Newest MCP transport. Similar tradeoffs to SSE.

**Why this wins**:
- **Personal use case**: Flo is the only user. The MCP server runs on the same machine as Claude Desktop/Code.
- **No auth needed**: The subprocess inherits the parent's environment (including `MAILROOM_JMAP_TOKEN`). No API keys to manage for the MCP layer itself.
- **Zero infrastructure**: No port, no reverse proxy, no TLS. The process starts when Claude needs it and exits when done.
- **FastMCP default**: `app.run()` defaults to stdio. Minimal code.

**When to revisit**: If a use case emerges for remote MCP access (e.g., running the MCP server on a VPS while using Claude Desktop locally). The tool definitions don't change — only the transport initialization.

---

## DEC-06: Warm client via lifespan

**Decision**: `JMAPClient.connect()` is called once during the FastMCP lifespan (app startup), and the connected client is stored on the app context for all tool invocations.

**Alternatives considered**:
- **Connect per-request**: Simple but adds ~200ms per tool call (JMAP session discovery). Wasteful since the session info rarely changes.
- **Module-level singleton**: Connects at import time. Fragile — fails if environment isn't configured when the module loads (e.g., during testing).

**Why this wins**:
- The FastMCP lifespan pattern is the idiomatic way to initialize resources. It's the equivalent of `__main__.py`'s startup sequence but for MCP.
- The connected client persists for the server's lifetime. Session reconnect can be added as a try/except in tool functions if the token expires.
- Clean testability — the lifespan can be mocked or replaced in tests.

```python
@asynccontextmanager
async def lifespan(app: FastMCP):
    settings = MailroomSettings()
    configure_logging(settings.logging.level)
    jmap = JMAPClient(token=settings.jmap_token)
    jmap.connect()
    yield {"jmap": jmap, "settings": settings}
```

---

## DEC-07: Logging strategy

**Decision**: The MCP server reuses `configure_logging()` from `mailroom.core.logging`. Logs go to stderr (structlog default), which is separate from the MCP stdio protocol on stdout.

**Alternatives considered**:
- **Separate logging config for MCP**: Unnecessary divergence. The same structured logging works.
- **Disable logging in MCP mode**: Loses observability. Debugging MCP issues requires logs.
- **Log to file instead of stderr**: More complex. stderr is the convention for MCP servers (stdout is the protocol channel).

**Why this wins**:
- MCP protocol uses stdout. structlog writes to stderr. No conflict.
- Same log format (JSON in prod, console in dev) regardless of entry point.
- Claude Desktop captures stderr and shows it in developer tools, making it useful for debugging.

---

## DEC-08: Email-first, contacts later

**Decision**: Phase 1 exposes only email tools (via `JMAPClient`). Contact tools come in Phase 2.

**Alternatives considered**:
- **Ship both email and contact tools together**: Larger blast radius. Contact operations (group membership, vCard manipulation) are more complex and have write-side effects.
- **Wait for JMAP Contacts migration**: Blocks the MCP server on a protocol refactor that doesn't change external behavior.

**Why this wins**:
- Fastest path to value. Email search/read/label covers the primary use case ("Claude, what did X send me?").
- CardDAV contact operations work today. When contact tools are added in Phase 2, they use the existing `CardDAVClient`.
- When/if Mailroom migrates from CardDAV to JMAP Contacts, the MCP contact tools benefit automatically (same Python interface, new protocol underneath).

---

## DEC-09: No read_email body parsing in Phase 1

**Decision**: `read_email` returns raw JMAP body parts (text/plain, text/html) without complex parsing, HTML-to-text conversion, or attachment handling.

**Alternatives considered**:
- **Full email rendering**: Parse MIME, extract attachments, convert HTML to markdown. Significant complexity for the initial release.
- **Text-only extraction**: Always return text/plain, fall back to stripped HTML. Lossy for HTML-only emails.

**Why this wins**:
- JMAP already returns structured body parts. Pass them through.
- Claude handles both plain text and HTML content natively.
- Keeps the initial implementation simple. Enhancements (attachment listing, selective body type) can be added per tool without changing the architecture.

---

## Summary Matrix

| Decision | Core Tradeoff | Revisit When |
|---|---|---|
| DEC-01: Monorepo | Simplicity vs. separation | Project grows to multiple maintainers |
| DEC-02: No config split | Zero overhead vs. flexibility | MCP-specific settings emerge |
| DEC-03: No workflow dep | Safety vs. reuse | Never (intentional boundary) |
| DEC-04: Sync in async | Zero refactor vs. purity | Migrate to async clients |
| DEC-05: stdio transport | Simplicity vs. remote access | Need remote MCP access |
| DEC-06: Warm client | Performance vs. simplicity | Never (lifespan is idiomatic) |
| DEC-07: Logging | Reuse vs. customization | MCP logging conflicts with stdio |
| DEC-08: Email-first | Speed to value vs. completeness | Phase 1 ships successfully |
| DEC-09: Raw body parts | Simplicity vs. polish | User feedback requests rendering |
