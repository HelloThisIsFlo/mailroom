# Project Research Summary

**Project:** Mailroom v1.1 -- Push & Config
**Domain:** JMAP EventSource push notifications, configurable triage categories, Fastmail setup automation
**Researched:** 2026-02-25
**Confidence:** HIGH

## Executive Summary

Mailroom v1.1 adds three improvements to a working v1.0 email triage service: JMAP EventSource push notifications (replacing fixed-interval polling with sub-10-second triage latency), configurable triage category mappings (replacing 18 hardcoded env vars with a structured JSON config), and a setup script (automating Fastmail mailbox and contact group provisioning). All three features extend the existing synchronous Python stack without architectural changes. The research is grounded in the live codebase (8,666 LOC inspected), empirical SSE behavior observed via a discovery script against live Fastmail, RFC 8620/8621 specifications, and pydantic-settings documentation. The entire milestone adds approximately 230 lines of production code and one new dependency (`httpx-sse`). Overall risk is LOW-MEDIUM.

The recommended build order is Config before Setup Script before EventSource. The config refactor is the foundation that both the setup script (which reads categories to know what to provision) and EventSource (which needs push config fields) depend on. Critically, the config migration must preserve backward compatibility with the existing 18 flat env vars and all 180 unit tests -- this is non-negotiable and the zero-test-breakage gate must pass before any other work proceeds. The setup script is a standalone tool that exercises new JMAP and CardDAV write operations, providing a useful validation gate before the more complex EventSource threading is introduced. EventSource is last because it has the highest complexity (daemon thread, debounce, reconnection, timeout tuning) and benefits from a stable foundation.

The most important risk is SSE silent connection death -- a state where the TCP socket appears open but no events are delivered, causing triage latency to silently regress from seconds to minutes with no visible error. Prevention requires ping-based liveness detection (read timeout = 65 seconds = 2x ping interval), explicit health endpoint reporting of SSE state, and keeping the polling fallback intact as an unconditional safety net. A second risk is the setup script's sieve rule gap: the script creates mailboxes and contact groups, but Fastmail routing rules cannot be created via any API. The script must output prominent human instructions for this manual step or users will think setup is complete when it is not.

## Key Findings

### Recommended Stack

The v1.0 stack is validated and unchanged. v1.1 adds exactly one new dependency. See [STACK.md](STACK.md) for full details.

**Core technologies:**
- `httpx-sse` 0.4.3 (NEW): SSE event parsing for JMAP EventSource -- the httpx-official companion library with zero new transitive dependencies. Replaces ~40 lines of fragile hand-rolled SSE parsing from the discovery script. 202 GitHub stars, maintained (Oct 2025 release).
- `httpx` 0.28.1 (existing): All HTTP transport including SSE streaming -- SSE client needs its own instance with `read=65.0, pool=None` timeout configuration, separate from the JMAP API client.
- `pydantic-settings` 2.13.1 (existing): Configurable categories via JSON-encoded env var -- `list[TriageCategory]` parsed natively with no additional library. Default value matches v1.0 behavior exactly.
- `threading` + `queue.Queue` (stdlib): SSE listener daemon thread with trigger-based wakeup -- no asyncio needed. Debounce and reconnection logic in ~30 lines of stdlib.

**What NOT to add:** `asyncio`/`anyio` (sync-by-design codebase, no benefit for single-user service), `tenacity` (simple manual backoff suffices for SSE reconnect loop), `click`/`typer` (argparse handles 2-3 flags in setup script), `pyyaml`/`toml` (JSON env var works for k8s ConfigMap; file-based config is v1.2).

### Expected Features

See [FEATURES.md](FEATURES.md) for full detail including complexity estimates (~230 total lines), dependency graph, and impact on existing files.

**Must have (table stakes -- defines the milestone):**
- EventSource SSE connection -- connect to `{eventSourceUrl}?types=Email,Mailbox&closeafter=no&ping=30` with Bearer auth; Fastmail wraps events in `{"type": "connect|change", "changed": {...}}` envelope (verified via discovery script).
- Debounced triage triggering -- accumulate SSE events over 3-second window, collapse batch arrivals into a single `workflow.poll()` call. Configurable via `MAILROOM_DEBOUNCE_SECONDS`.
- Polling fallback -- `trigger.wait(poll_interval=300)` timeout ensures triage runs even if SSE is silent. SSE is an optimization, not a replacement.
- Configurable triage category mapping -- optional `MAILROOM_TRIAGE_CATEGORIES` JSON env var replaces 18 individual vars; default matches v1.0 behavior exactly; validated at startup via pydantic.
- Setup script: mailbox provisioning -- `Mailbox/set` create for each required label and destination mailbox not yet present in Fastmail. Idempotent check-then-create.
- Setup script: contact group provisioning -- CardDAV PUT of Apple-style group vCard (`KIND:group`) for each missing contact group. Same pattern as existing `create_contact()`.

**Should have (ship if time allows):**
- SSE health status in `/healthz` -- `eventsource_connected` and `eventsource_thread_alive` fields; LOW complexity, HIGH operational value.
- Setup script dry-run mode -- `--dry-run` flag prints what would be created; builds confidence before touching production account.
- Migration docs -- show old ConfigMap and equivalent new `MAILROOM_TRIAGE_CATEGORIES` format.

**Defer to v1.2:**
- Debounce escalation on SSE disconnect (nice-to-have faster recovery, not essential)
- Sieve rule validation in setup script (no Fastmail API; document manual steps instead)
- YAML config file source for categories (JSON env var sufficient for k8s)
- Per-event-type processing (premature optimization; `workflow.poll()` is fast and idempotent)
- Nested mailbox hierarchy support (flat namespace only in v1.1)

### Architecture Approach

The architecture is an additive extension of v1.0's synchronous single-process model. A new `EventSourceListener` daemon thread signals the existing main loop via `threading.Event` instead of a fixed sleep. The config layer gains a `TriageCategory` model and optional categories list while keeping all existing flat env var paths functional. A new `setup.py` entry point reuses existing JMAP and CardDAV clients with two new write methods each. The `ScreenerWorkflow.poll()` interface is entirely unchanged. See [ARCHITECTURE.md](ARCHITECTURE.md) for full data flow diagrams and exact code sketches.

**Major components (new and modified):**
1. `EventSourceListener` (new, `clients/eventsource.py`) -- SSE connection, event filtering by type, debounce timer, exponential backoff reconnection (1s/2s/4s/max 60s), health state reporting.
2. `TriageCategory` model + updated `MailroomSettings` (modified, `core/config.py`) -- optional structured category list with backward-compatible fallback to existing flat fields; all derived properties (`triage_labels`, `contact_groups`, `required_mailboxes`) compute from the mapping, never from individual fields.
3. Setup script (new, `setup.py`) -- idempotent check-then-create for mailboxes and contact groups; prints sieve rule instructions for the manual step; requires explicit `--apply` to make changes.
4. Modified main loop (`__main__.py`) -- replaces `shutdown_event.wait(poll_interval)` with `trigger.wait(poll_interval)` where trigger is set by SSE or timeout; monitors SSE thread liveness each cycle.
5. New client methods -- `JMAPClient.create_mailbox()` and `CardDAVClient.create_group()` (used only by setup script, not main service path).

### Critical Pitfalls

Top pitfalls across all research. See [PITFALLS.md](PITFALLS.md) for full prevention strategies, detection signals, and a "Looks Done But Isn't" checklist.

1. **SSE silent connection death** -- TCP socket appears open, no events delivered, service silently degrades to polling-only. Prevention: read timeout = 65s (2x ping interval + 5s buffer); log `eventsource_alive` with event counter periodically; expose `eventsource_connected` and `last_sse_event_age_seconds` in health endpoint; never remove polling fallback. Build liveness detection from day one.

2. **Config migration breaks 180 tests** -- Any structural change to config that removes flat env vars breaks every test. Prevention: make `triage_categories` optional; flat fields remain the default path; all 180 tests pass with zero modifications (use this as the compatibility gate before touching any test file).

3. **Derived properties miss new categories** -- `required_mailboxes` and `contact_groups` return the hardcoded flat-field set even after a custom category is added, causing runtime `KeyError` when the category is first used. Prevention: compute ALL validation lists from `label_to_group_mapping`, not individual fields. Add a test that configures a custom category and verifies it appears in all three derived properties.

4. **Setup script sieve rule gap** -- Script creates labels and groups but cannot create Fastmail routing rules (no JMAP/CardDAV API). Users think setup is complete but future emails still route to Screener. Prevention: output must include a prominently numbered post-setup checklist with human-readable sieve rule instructions; do not bury this as a footnote.

5. **SSE thread dies silently** -- Daemon thread crashes with unhandled `httpx.RemoteProtocolError`; main loop continues in polling-only mode with no visible error. Prevention: main loop checks `sse_thread.is_alive()` each poll cycle and restarts thread; catch-all handler in listener logs full traceback; health endpoint reports thread state.

## Implications for Roadmap

Based on combined research, three phases are recommended. The dependency graph is clear and unambiguous. All phases ship independently useful improvements.

### Phase 1: Configurable Categories

**Rationale:** Config is the foundation. Both the setup script (reads categories to know what to provision) and EventSource (push_enabled, debounce_seconds fields) depend on a stable config model. Building config first also validates backward compatibility before any other complexity is introduced. The litmus test is simple: all 180 existing tests pass with zero test file modifications.

**Delivers:** Optional `MAILROOM_TRIAGE_CATEGORIES` JSON env var; `TriageCategory` pydantic model; backward-compatible derived properties (`triage_labels`, `contact_groups`, `required_mailboxes`) that include custom categories in startup validation; `add_inbox_label` field replaces hardcoded Imbox check in `ScreenerWorkflow`.

**Addresses:** Configurable triage category mapping (table stakes #4 from FEATURES.md).

**Avoids:** Pitfall 2 (config migration breaks tests -- backward-compatible design), Pitfall 9 (derived properties miss new categories -- compute from mapping), Pitfall 5 (JSON env var ergonomics -- ship defaults that match v1.0 exactly so zero-change deployments work).

**Risk:** LOW. Internal config refactor. No new dependencies. No new threads. All changes invisible to workflow consumers.

### Phase 2: Setup Script

**Rationale:** Depends on Phase 1 (reads `triage_categories` to know what to provision). Exercises new JMAP write operations (`Mailbox/set` create) and CardDAV write operations (group vCard PUT) that have not been used in the codebase before. Validating these against live Fastmail before the main service depends on them is prudent. The setup script is fully independent of EventSource and cannot break the running service.

**Delivers:** `mailroom-setup` CLI with idempotent check-then-create logic; `JMAPClient.create_mailbox()`; `CardDAVClient.create_group()`; sieve rule instructions in output; account confirmation before applying changes.

**Addresses:** Setup script mailbox provisioning and contact group provisioning (table stakes #5 and #6 from FEATURES.md). Dry-run mode (differentiator) if time allows.

**Avoids:** Pitfall 4 (sieve rule gap -- output includes prominent manual instructions with numbered checklist), Pitfall 7 (idempotency failure -- check-then-create, report exists vs. created), Pitfall 13 (wrong credentials -- print account info and require `--apply` flag), Pitfall 11 (mailbox hierarchy -- flat namespace only in v1.1).

**Risk:** MEDIUM. `Mailbox/set` create is a new JMAP operation. Fastmail's name-uniqueness enforcement for sibling mailboxes needs live testing. CardDAV group creation follows the same pattern as existing `create_contact()`.

### Phase 3: EventSource Push

**Rationale:** Highest complexity; rightfully last. Depends on Phase 1 (push config fields: `push_enabled`, `debounce_seconds`, `sse_ping_interval`) but not on Phase 2. Building last means the service is fully functional with polling before push is layered on, providing a clean fallback state if push is broken or rolled back. The threading model requires the most careful design of any feature in this milestone.

**Delivers:** `EventSourceListener` class in `clients/eventsource.py`; modified main loop with `trigger.wait(poll_interval)` replacing fixed sleep; SSE thread lifecycle management; health endpoint expansion; `httpx-sse` dependency; triage latency reduced from up to 5 minutes to ~6-9 seconds (~1s SSE propagation + 3s debounce + 2-5s poll execution).

**Addresses:** EventSource SSE connection, debounced triage triggering, polling fallback (table stakes #1, #2, #3 from FEATURES.md). SSE health in /healthz (differentiator).

**Avoids:** Pitfall 1 (silent connection death -- liveness detection built in from day one, read=65s timeout), Pitfall 3 (reconnect thundering herd -- "skip if recently polled" guard), Pitfall 6 (thread death -- main loop monitors `is_alive()` and restarts), Pitfall 8 (timeout misconfiguration -- dedicated httpx client with read=65s, pool=None), Pitfall 10 (debounce too short -- configurable, empirical tuning via human test).

**Risk:** MEDIUM-HIGH. Long-lived SSE connections have known production failure modes (proxy buffering, TCP half-open, silent death). The threading model is new to the codebase. Polling fallback ensures graceful degradation: push failures degrade to v1.0 behavior rather than outages.

### Phase Ordering Rationale

- Config first: no external dependencies; zero-breakage gate validates the migration approach before adding complexity.
- Setup script second: exercises new Fastmail write operations against live infrastructure; standalone tool that cannot break the running service; validates JMAP and CardDAV write paths before EventSource adds threading complexity.
- EventSource last: highest complexity; depends on stable config; service remains fully operational through phases 1 and 2.
- Each phase ships independently deployable improvements: configurable categories are useful without push; the setup script reduces onboarding friction regardless of push timing.

### Research Flags

Phases with well-documented patterns (skip `/gsd:research-phase`):
- **Phase 1 (Configurable Categories):** pydantic-settings JSON env var parsing is documented with working examples. Config backward compatibility pattern is explicit. No unknowns.
- **Phase 2 (Setup Script):** JMAP `Mailbox/set` create is RFC 8621 standard. CardDAV group vCard format is validated in the existing `validate_groups()` method. The only live-testing question is Fastmail's name-uniqueness error response format on duplicate create -- test this in the Phase 2 human test before relying on it for idempotency.

Phases that may benefit from targeted research or tuning during implementation:
- **Phase 3 (EventSource):** SSE timeout values (read=65s is calculated, not empirically validated against Fastmail's production infrastructure). Debounce window (3s default is a starting point; needs measurement against live label-application latency). Proxy/network behavior in the k8s deployment environment may affect SSE connection stability and require tuning of `MAILROOM_SSE_PING_INTERVAL`.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | One new dependency (httpx-sse) with well-understood integration pattern. All existing stack decisions validated in production v1.0. |
| Features | HIGH | Scope tightly defined. Feature dependencies clear. Complexity estimates grounded in codebase inspection. ~230 total lines of new production code. |
| Architecture | HIGH | Additive extension of v1.0. RFC 8620/8621 specs verified. Fastmail SSE envelope format empirically observed via discovery script. pydantic-settings JSON parsing confirmed via docs. |
| Pitfalls | MEDIUM-HIGH | SSE pitfalls well-documented in production literature. Config pitfalls derived from direct codebase analysis. Gap: SSE connection behavior in production k8s environment (proxy/LB behavior) not yet observed. |

**Overall confidence:** HIGH

### Gaps to Address

- **SSE read timeout tuning:** The 65-second read timeout is calculated from the ping interval (2 x 30s + 5s buffer). The actual Fastmail SSE connection stability under the k8s network environment may require adjustment. Build configurable `MAILROOM_SSE_PING_INTERVAL` in Phase 1 so this can be tuned without code changes.

- **Debounce window empirical validation:** The 3-second default has not been measured against live label-application-to-JMAP-query consistency lag. Human test `test_15_eventsource_push.py` should measure the actual gap before the debounce value is finalized.

- **Fastmail mailbox name-uniqueness error format:** The `Mailbox/set` create behavior when a sibling mailbox with the same name already exists needs live validation. RFC says it MUST be rejected, but the `notCreated` error object format is implementation-specific. Test this in Phase 2 before relying on it for idempotency logic.

- **@ToPerson scope with custom categories:** Kept as-is for v1.1 (routes to Imbox only). Users adding custom categories who want person-type contacts must create a separate label (e.g., `@ToBillboardPerson`). Document this limitation in the `TriageCategory` schema and config reference.

## Sources

### Primary (HIGH confidence)
- [RFC 8620 Section 7.3: Event Source](https://www.rfc-editor.org/rfc/rfc8620#section-7.3) -- JMAP EventSource specification, query parameters, SSE format
- [RFC 8621: JMAP for Mail](https://www.rfc-editor.org/rfc/rfc8621.html) -- Mailbox/set create properties, name uniqueness constraints
- [httpx-sse v0.4.3 PyPI](https://pypi.org/project/httpx-sse/) -- SSE client library for httpx; sync + async support; Python 3.9-3.13
- [httpx Third Party Packages](https://www.python-httpx.org/third_party_packages/) -- httpx-sse listed as official httpx companion
- [pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- JSON env var parsing for complex types including list[BaseModel]
- [W3C Server-Sent Events specification](https://html.spec.whatwg.org/multipage/server-sent-events.html) -- Keepalive comment convention, reconnection behavior
- [CardDAV Group Implementation](https://github.com/mstilkerich/rcmcarddav/blob/master/doc/GROUPS.md) -- X-ADDRESSBOOKSERVER-KIND group vCard format
- Mailroom codebase (`src/mailroom/`, `tests/`, `human-tests/`, `k8s/`) -- directly inspected, 8,666 LOC
- `.research/jmap-eventsource/jmap-eventsource.md` -- Fastmail SSE envelope format, observed event types, empirical connection behavior
- `.research/jmap-eventsource/integration-sketch.md` -- Thread architecture, debounce pattern, code-level integration plan

### Secondary (MEDIUM confidence)
- [Fastmail blog: EventSource/SSE](https://www.fastmail.com/blog/building-the-new-ajax-mail-ui-part-1-instant-notifications-of-new-emails-via-eventsourceserver-sent-events/) -- Connection timeout behavior, reconnection gotchas
- [Fastmail JMAP-Samples #7](https://github.com/fastmail/JMAP-Samples/issues/7) -- Third-party EventSource auth requirements, personal API tokens required
- [SSE production issues](https://dev.to/miketalbot/server-sent-events-are-still-not-production-ready-after-a-decade-a-lesson-for-me-a-warning-for-you-2gie) -- Real-world SSE pitfalls: proxy buffering, connection drops, silent failures
- [SSE idle connection reset: seqeralabs/nf-tower#48](https://github.com/seqeralabs/nf-tower/issues/48) -- SSE connections resetting at 5 minutes
- [TCP half-open connection detection](https://blog.stephencleary.com/2009/05/detection-of-half-open-dropped.html) -- Why TCP connections can appear alive when dead
- [pydantic/pydantic-settings#203](https://github.com/pydantic/pydantic-settings/issues/203) -- Known limitations with deeply nested models in env vars

---
*Research completed: 2026-02-25*
*Ready for roadmap: yes*
