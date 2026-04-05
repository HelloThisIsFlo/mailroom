# MCP Architecture for Mailroom

> **Status**: Architecture reference (pre-implementation)
> **Related files**: [decisions.md](decisions.md) | [index.html](index.html) (interactive visual)

## The "Two Front Doors" Concept

Mailroom gains a **dual identity**: it remains an automated triage backend (the polling service) while also becoming an interactive email access layer for Claude via MCP. Both identities share the same foundation — clients, config, and credentials — but serve fundamentally different purposes.

| Identity | Purpose | Trigger | Runs As |
|---|---|---|---|
| **Polling Service** | Automated email triage | SSE events / timer | Long-running daemon (`mailroom run`) |
| **MCP Server** | Interactive email access | Claude tool calls | stdio subprocess (`mailroom mcp`) |

The key insight: **the hard work is already done**. The JMAP and CardDAV clients are battle-tested, protocol-correct, and cleanly separated from the automation logic. The MCP server is a new *interface* on top of existing *infrastructure*.

## Architecture: Before & After

### Current Architecture

```mermaid
graph TB
    subgraph "Entry Points"
        CLI["mailroom CLI<br/>(click)"]
        MAIN["__main__.py<br/>polling loop"]
    end

    subgraph "Workflows"
        SW["ScreenerWorkflow<br/>poll() orchestration"]
    end

    subgraph "Clients"
        JMAP["JMAPClient<br/>JMAP over httpx"]
        CARDDAV["CardDAVClient<br/>CardDAV over httpx"]
    end

    subgraph "Core"
        CONFIG["MailroomSettings<br/>pydantic-settings + YAML"]
        LOG["configure_logging<br/>structlog"]
    end

    subgraph "External"
        FM_JMAP["Fastmail JMAP API"]
        FM_CARD["Fastmail CardDAV"]
    end

    CLI --> MAIN
    MAIN --> SW
    MAIN --> CONFIG
    MAIN --> LOG
    SW --> JMAP
    SW --> CARDDAV
    JMAP --> FM_JMAP
    CARDDAV --> FM_CARD
```

### Future Architecture (with MCP)

```mermaid
graph TB
    subgraph "Entry Points"
        CLI["mailroom CLI<br/>(click)"]
        MAIN["__main__.py<br/>polling loop"]
        MCP["MCP Server<br/>(FastMCP, stdio)"]
    end

    subgraph "Workflows"
        SW["ScreenerWorkflow<br/>poll() orchestration"]
    end

    subgraph "MCP Layer"
        TOOLS["mcp/tools.py<br/>tool definitions"]
        LIFE["mcp/server.py<br/>lifespan + app"]
    end

    subgraph "Clients"
        JMAP["JMAPClient<br/>JMAP over httpx"]
        CARDDAV["CardDAVClient<br/>CardDAV over httpx"]
    end

    subgraph "Core"
        CONFIG["MailroomSettings<br/>pydantic-settings + YAML"]
        LOG["configure_logging<br/>structlog"]
    end

    subgraph "External"
        FM_JMAP["Fastmail JMAP API"]
        FM_CARD["Fastmail CardDAV"]
    end

    CLI --> MAIN
    CLI -.-> MCP
    MAIN --> SW
    MAIN --> CONFIG
    MAIN --> LOG
    MCP --> LIFE
    LIFE --> CONFIG
    LIFE --> LOG
    LIFE --> JMAP
    TOOLS --> JMAP
    SW --> JMAP
    SW --> CARDDAV
    JMAP --> FM_JMAP
    CARDDAV --> FM_CARD

    style MCP fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style TOOLS fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style LIFE fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
```

## Package Structure Evolution

```
src/mailroom/
    __init__.py
    __main__.py          # polling service entry point (UNTOUCHED)
    cli.py               # click CLI (ADD: 2-line `mcp` subcommand)
    eventsource.py       # SSE listener (UNTOUCHED)

    core/
        __init__.py
        config.py        # MailroomSettings (UNTOUCHED)
        logging.py       # structlog config (UNTOUCHED)

    clients/
        __init__.py
        jmap.py          # JMAPClient (UNTOUCHED)
        carddav.py       # CardDAVClient (UNTOUCHED)

    workflows/
        __init__.py
        screener.py      # ScreenerWorkflow (UNTOUCHED)

    setup/               # (UNTOUCHED)
    reset/               # (UNTOUCHED)

    mcp/                 # NEW - entire directory
        __init__.py      # NEW - empty
        server.py        # NEW - FastMCP app + lifespan
        tools.py         # NEW - tool definitions
```

**Files touched**: 3 new + 2 modified (`cli.py` gets a subcommand, `pyproject.toml` gets the `mcp` dependency and entry point). **Zero changes** to existing business logic.

## Layer Diagram

```mermaid
graph TB
    subgraph "Interface Layer (independent)"
        direction LR
        POLL["Polling Service<br/>__main__.py + eventsource.py"]
        MCPS["MCP Server<br/>mcp/server.py + mcp/tools.py"]
    end

    subgraph "Business Logic (polling only)"
        SW["ScreenerWorkflow<br/>workflows/screener.py"]
    end

    subgraph "Shared Foundation"
        direction LR
        JMAP["JMAPClient"]
        CARDDAV["CardDAVClient"]
        CONFIG["MailroomSettings"]
        LOG["Logging"]
    end

    POLL --> SW
    SW --> JMAP
    SW --> CARDDAV
    MCPS --> JMAP
    POLL --> CONFIG
    POLL --> LOG
    MCPS --> CONFIG
    MCPS --> LOG
```

Critical observation: **the MCP server never imports from `workflows/`**. It talks directly to the clients. The ScreenerWorkflow contains automation policy (conflict detection, retry safety, triage label sequencing) that doesn't belong in interactive tools.

## Dependency Flow

```mermaid
graph LR
    subgraph "Polling Path"
        direction TB
        A["__main__.py"] --> B["ScreenerWorkflow"]
        B --> C["JMAPClient"]
        B --> D["CardDAVClient"]
        A --> E["MailroomSettings"]
        A --> F["configure_logging"]
    end

    subgraph "MCP Path"
        direction TB
        G["mcp/server.py"] --> H["mcp/tools.py"]
        H --> I["JMAPClient"]
        G --> J["MailroomSettings"]
        G --> K["configure_logging"]
    end

    style C fill:#fff3e0,stroke:#e65100
    style I fill:#fff3e0,stroke:#e65100
    style E fill:#e3f2fd,stroke:#1565c0
    style J fill:#e3f2fd,stroke:#1565c0
```

The two paths share `JMAPClient` and `MailroomSettings` (highlighted) but diverge at the logic layer. The polling path goes through `ScreenerWorkflow`; the MCP path goes directly to tools.

## Data Flow Diagrams

### MCP Tool Call Flow

```mermaid
sequenceDiagram
    participant Claude
    participant MCP as MCP Server (stdio)
    participant Tools as tools.py
    participant JMAP as JMAPClient
    participant FM as Fastmail API

    Note over MCP: Lifespan: connect JMAPClient once at startup

    Claude->>MCP: search_emails(query="from:alice@...")
    MCP->>Tools: search_emails(ctx, query)
    Tools->>JMAP: query_emails(mailbox_id, sender)
    JMAP->>FM: Email/query (JMAP POST)
    FM-->>JMAP: {ids: [...]}
    JMAP-->>Tools: [email_id_1, email_id_2]
    Tools->>JMAP: get_email_senders(ids)
    JMAP->>FM: Email/get (JMAP POST)
    FM-->>JMAP: {list: [...]}
    JMAP-->>Tools: {id: (email, name)}
    Tools-->>MCP: formatted result
    MCP-->>Claude: tool response (JSON)
```

### Polling Service Flow

```mermaid
sequenceDiagram
    participant SSE as EventSource (SSE)
    participant Main as __main__.py
    participant SW as ScreenerWorkflow
    participant JMAP as JMAPClient
    participant CARDDAV as CardDAVClient
    participant FM as Fastmail

    SSE->>Main: state change event
    Main->>Main: debounce (1s)
    Main->>SW: poll()
    SW->>JMAP: batched Email/query (all labels)
    JMAP->>FM: JMAP POST
    FM-->>JMAP: responses
    JMAP-->>SW: label_email_ids
    SW->>SW: detect conflicts
    SW->>CARDDAV: upsert_contact()
    CARDDAV->>FM: CardDAV PUT
    FM-->>CARDDAV: 201 Created
    SW->>JMAP: reconcile email labels
    JMAP->>FM: Email/set
    FM-->>JMAP: updated
    SW->>JMAP: remove triage label (LAST)
    JMAP->>FM: Email/set
```

## Initialization Sequence Comparison

```mermaid
graph TB
    subgraph "Polling Service (__main__.py)"
        direction TB
        P1["Load MailroomSettings()"] --> P2["configure_logging()"]
        P2 --> P3["JMAPClient.connect()"]
        P3 --> P4["CardDAVClient.connect()"]
        P4 --> P5["resolve_mailboxes()"]
        P5 --> P6["validate_groups()"]
        P6 --> P7["Build ScreenerWorkflow"]
        P7 --> P8["Start health server"]
        P8 --> P9["Start SSE listener"]
        P9 --> P10["Enter polling loop"]
    end

    subgraph "MCP Server (lifespan)"
        direction TB
        M1["Load MailroomSettings()"] --> M2["configure_logging()"]
        M2 --> M3["JMAPClient.connect()"]
        M3 --> M4["Store on app context"]
        M4 --> M5["yield (server ready)"]
        M5 --> M6["Cleanup on shutdown"]
    end

    style P4 fill:#fff3e0,stroke:#e65100
    style P5 fill:#fff3e0,stroke:#e65100
    style P6 fill:#fff3e0,stroke:#e65100
    style P7 fill:#fff3e0,stroke:#e65100
    style P8 fill:#fff3e0,stroke:#e65100
    style P9 fill:#fff3e0,stroke:#e65100
```

The MCP lifespan is deliberately **simpler** — no CardDAV, no mailbox resolution, no workflow, no health server. It just needs a warm JMAPClient. The orange-highlighted steps in the polling path are automation-specific concerns that the MCP server doesn't need.

## Config Sharing

Both entry points load the same `MailroomSettings`:

```python
# __main__.py (polling)
settings = MailroomSettings()  # reads config.yaml + MAILROOM_* env vars
jmap = JMAPClient(token=settings.jmap_token)

# mcp/server.py (MCP lifespan)
settings = MailroomSettings()  # same config, same env vars
jmap = JMAPClient(token=settings.jmap_token)
```

**One config file, one set of credentials, two interfaces.** The MCP server doesn't need its own config — it inherits everything from the existing `config.yaml` and `MAILROOM_*` environment variables.

The MCP server may use `settings.triage.categories` to present mailbox context (e.g., "these are your triage categories") but doesn't enforce triage rules.

## MCP Tool Catalog

Phase 1 focuses on **email-only tools** using `JMAPClient`:

| Tool | Description | Maps to JMAPClient Method(s) |
|---|---|---|
| `list_mailboxes` | List all Fastmail mailboxes with IDs | `resolve_mailboxes()` (or raw `Mailbox/get`) |
| `search_emails` | Search emails by mailbox and/or sender | `query_emails()`, `query_emails_by_sender()` |
| `read_email` | Get full email content by ID | New: `Email/get` with body properties |
| `get_email_headers` | Get sender/subject/date for email IDs | `get_email_senders()` (extended) |
| `add_labels` | Add mailbox labels to emails | `batch_add_labels()` |
| `remove_labels` | Remove mailbox labels from emails | `batch_remove_labels()` |
| `move_email` | Move email between mailboxes | Combo: `batch_add_labels()` + `batch_remove_labels()` |

```mermaid
graph LR
    subgraph "MCP Tools"
        T1[list_mailboxes]
        T2[search_emails]
        T3[read_email]
        T4[get_email_headers]
        T5[add_labels]
        T6[remove_labels]
        T7[move_email]
    end

    subgraph "JMAPClient Methods"
        M1["resolve_mailboxes()"]
        M2["query_emails()"]
        M3["query_emails_by_sender()"]
        M4["Email/get (new)"]
        M5["get_email_senders()"]
        M6["batch_add_labels()"]
        M7["batch_remove_labels()"]
    end

    T1 --> M1
    T2 --> M2
    T2 --> M3
    T3 --> M4
    T4 --> M5
    T5 --> M6
    T6 --> M7
    T7 --> M6
    T7 --> M7
```

### Future Tools (Phase 2+)

| Tool | Description | Client |
|---|---|---|
| `list_contacts` | Browse contacts in a group | CardDAVClient |
| `search_contacts` | Find contact by email | CardDAVClient |
| `get_triage_status` | Show pending triage emails | JMAPClient |
| **Resources** | | |
| `mailroom://categories` | Current triage category config | MailroomSettings |
| `mailroom://mailboxes` | Mailbox name-to-ID mapping | JMAPClient |
| **Prompts** | | |
| `triage-helper` | Guide user through manual triage | Combo |

## Key Design Decisions

> Full rationale in [decisions.md](decisions.md)

1. **Monorepo** — one package, one venv, one test suite. The MCP server imports `mailroom.clients.jmap` directly.
2. **No config split** — same `config.yaml` + `MAILROOM_*` env vars serve both identities.
3. **No workflow dependency** — `mcp/tools.py` never imports from `workflows/`. Interactive tools are deliberate, not automated.
4. **Sync client in async tools** — JMAPClient uses `httpx.Client` (sync). FastMCP tools are async but call sync methods directly (fine for stdio single-concurrency).
5. **stdio transport** — Claude Desktop/Code launches the MCP server as a subprocess. No HTTP server needed.
6. **Warm client via lifespan** — `JMAPClient.connect()` runs once at startup, stored on app context. Not per-request.

## Entry Points Summary

```toml
# pyproject.toml
[project.scripts]
mailroom = "mailroom.cli:cli"         # existing
mailroom-mcp = "mailroom.mcp:main"    # new
```

```python
# cli.py addition
@cli.command()
def mcp():
    """Start the MCP server (stdio transport)."""
    from mailroom.mcp.server import app
    app.run()
```

## Future Evolution

1. **Contact tools** — Add CardDAV-backed tools for browsing/searching contacts. These work with the existing `CardDAVClient` as-is.
2. **JMAP Contacts migration** — When Fastmail's JMAP Contacts API stabilizes and Mailroom migrates from CardDAV, the MCP contact tools automatically benefit (same interface, new protocol underneath).
3. **MCP Resources** — Expose category config and mailbox mappings as MCP resources for context injection.
4. **MCP Prompts** — Pre-built conversation templates like "triage helper" that guide Claude through interactive email management.
5. **SSE transport** — If remote access is ever needed (unlikely for personal use), swap stdio for SSE. The tool definitions don't change.
