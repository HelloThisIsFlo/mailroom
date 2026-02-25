# Phase 1: Foundation and JMAP Client - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Configuration system, structured logging, and a working JMAP client that can authenticate with Fastmail, resolve mailboxes, query emails by label, extract senders, move emails between mailboxes, and relabel them. Also includes Python project scaffolding with dependency management and test infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Configuration Shape
- All env vars prefixed with `MAILROOM_` (e.g. `MAILROOM_JMAP_TOKEN`, `MAILROOM_POLL_INTERVAL`)
- Sensible defaults for non-credential config: poll interval = 5 min, standard label names (@ToImbox, @ToFeed, @ToPaperTrail, @ToJail), standard group names (Imbox, Feed, Paper Trail, Jail)
- Credentials are required — service fails if JMAP token or CardDAV password is missing
- Log level controlled via `MAILROOM_LOG_LEVEL` env var (default: info)

### Startup Behavior
- Fail fast if any configured triage labels don't exist as mailboxes in Fastmail — catches typos before polling starts
- Validate that all 4 contact groups exist via CardDAV at startup — catches setup issues early
- Always log resolved config summary at startup (label names, group names, poll interval) at info level so it's visible in kubectl logs

### Log Output
- Structured JSON logs
- Info level: only log when actually processing a triage email (silent when nothing to do)
- Debug level: log one line per poll cycle ("poll: 0 triage emails found")
- Always log resolved config at startup regardless of level
- Detail level for triage actions at Claude's discretion

### Project Scaffolding
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

</decisions>

<specifics>
## Specific Ideas

- User wants log levels to map to operational modes: debug = setup/troubleshooting (verbose), info = production (quiet unless acting)
- Config should "just work" with the user's existing Fastmail setup — defaults match their current label and group names

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-and-jmap-client*
*Context gathered: 2026-02-24*
