---
phase: quick-4
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - human-tests/test_14_eventsource.py
  - .research/jmap-eventsource.md
autonomous: true
requirements: [TODO-3, TODO-4]

must_haves:
  truths:
    - "Script connects to Fastmail JMAP EventSource endpoint and receives SSE events"
    - "Events are logged with timestamps, type, and parsed payload"
    - "Research document captures RFC 8620 section 7.3 EventSource spec details"
    - "Research document records observed Fastmail event patterns and implications for future push architecture"
  artifacts:
    - path: "human-tests/test_14_eventsource.py"
      provides: "Standalone JMAP EventSource discovery script"
      min_lines: 60
    - path: ".research/jmap-eventsource.md"
      provides: "EventSource research findings and push architecture notes"
      min_lines: 40
  key_links:
    - from: "human-tests/test_14_eventsource.py"
      to: "https://api.fastmail.com/jmap/session"
      via: "JMAPClient.connect() for session discovery"
      pattern: "client\\.connect\\(\\)"
    - from: "human-tests/test_14_eventsource.py"
      to: "https://api.fastmail.com/jmap/event/"
      via: "httpx streaming GET with text/event-stream"
      pattern: "event-stream|eventSourceUrl"
---

<objective>
Create a JMAP EventSource discovery script and research document for understanding Fastmail's push notification patterns.

Purpose: Before implementing push-based architecture (replacing polling), we need empirical data on how Fastmail's JMAP EventSource behaves -- event frequency, payload shape, which state changes trigger events, and practical debounce windows.

Output: A human test script that connects to the SSE endpoint and logs events in real-time, plus a research document capturing spec details and observed patterns.
</objective>

<execution_context>
@/Users/flo/.claude/get-shit-done/workflows/execute-plan.md
@/Users/flo/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@src/mailroom/clients/jmap.py
@src/mailroom/core/config.py
@human-tests/test_1_auth.py

<interfaces>
<!-- Key types and contracts the executor needs -->

From src/mailroom/clients/jmap.py:
```python
class JMAPClient:
    def __init__(self, token: str, hostname: str = "api.fastmail.com") -> None: ...
    def connect(self) -> None:
        """Fetches session from https://{hostname}/jmap/session.
        Session JSON includes 'eventSourceUrl' field (https://api.fastmail.com/jmap/event/).
        Sets self._account_id and self._api_url."""
    @property
    def account_id(self) -> str: ...
```

From src/mailroom/core/config.py:
```python
class MailroomSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILROOM_", case_sensitive=False)
    jmap_token: str  # Required, no default
```

JMAP session response (confirmed from live Fastmail):
```json
{
  "eventSourceUrl": "https://api.fastmail.com/jmap/event/",
  "primaryAccounts": {"urn:ietf:params:jmap:mail": "<account-id>"},
  ...
}
```

RFC 8620 section 7.3 EventSource URL format:
  GET {eventSourceUrl}?types={types}&closeafter={state|no}&ping={seconds}
  Headers: Authorization: Bearer {token}, Accept: text/event-stream
  URL params:
    - types: comma-separated JMAP type names (e.g., "Email,Mailbox") or "*" for all
    - closeafter: "state" (close after first event) or "no" (keep open)
    - ping: seconds between keepalive pings (positive integer)
  SSE event format:
    - event: "state"
    - data: JSON object mapping accountId -> { typeName: newState, ... }
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create JMAP EventSource discovery script</name>
  <files>human-tests/test_14_eventsource.py</files>
  <action>
Create `human-tests/test_14_eventsource.py` following the established human test pattern:

1. Standard boilerplate: docstring, dotenv load from parent.parent / ".env", import JMAPClient + MailroomSettings.

2. Connect to JMAP session using `JMAPClient(token=settings.jmap_token)` + `client.connect()`. Then fetch the raw session JSON separately to extract `eventSourceUrl` (the JMAPClient does not expose this field -- make a direct httpx GET to `https://api.fastmail.com/jmap/session` with Bearer token to get it).

3. Build the EventSource URL per RFC 8620 section 7.3:
   - Base URL: the `eventSourceUrl` from session (confirmed: `https://api.fastmail.com/jmap/event/`)
   - Query params: `types=*` (all types to discover what fires), `closeafter=no` (keep connection open), `ping=30` (30-second keepalive)

4. Use `httpx.Client.stream("GET", url, headers={"Accept": "text/event-stream"})` to open a streaming SSE connection. Do NOT add a third-party SSE library -- parse the text/event-stream format manually since it is simple:
   - Lines starting with "event:" set the event type
   - Lines starting with "data:" contain the payload (JSON)
   - Lines starting with ":" are comments/keepalive pings
   - Empty lines delimit events

5. For each received event, print a structured log line:
   ```
   [2026-02-25T14:30:05.123] event=state
     Account: u12345678
       Email -> "abc123"
       Mailbox -> "def456"
       Thread -> "ghi789"
   ```
   For ping/comment lines, print: `[timestamp] ping (keepalive)`

6. Handle Ctrl+C gracefully: catch KeyboardInterrupt, print a summary of total events received, total time connected, and event frequency, then exit cleanly.

7. Add a `--duration` argument (default: 60 seconds) using argparse so the user can control how long to listen. After duration expires, print the same summary and exit. Print instructions at startup telling the user to trigger email activity (send themselves an email, apply a label) to see events.

8. Print PASS at the end if at least one state event was received. Print FAIL with troubleshooting hints if zero events after the full duration.

Important: Use `client._token` (the stored token) for the Authorization header on the EventSource request since JMAPClient does not expose the token publicly. Alternatively, just use `settings.jmap_token` directly which is cleaner.
  </action>
  <verify>
    python human-tests/test_14_eventsource.py --duration 10
    (should connect, receive at least ping keepalives within 10 seconds, and exit cleanly)
  </verify>
  <done>Script connects to Fastmail EventSource, parses SSE events, logs them with timestamps and structured payloads, handles Ctrl+C and --duration timeout gracefully, prints PASS/FAIL summary</done>
</task>

<task type="auto">
  <name>Task 2: Write EventSource research document</name>
  <files>.research/jmap-eventsource.md</files>
  <action>
Create `.research/jmap-eventsource.md` documenting JMAP EventSource for future push architecture work. Structure:

1. **Overview**: What JMAP EventSource is (RFC 8620 section 7.3), how it relates to Server-Sent Events (SSE), and why it matters for Mailroom (replacing polling with push).

2. **Spec Details** (from RFC 8620 section 7.3):
   - URL format: `{eventSourceUrl}?types={types}&closeafter={state|no}&ping={seconds}`
   - Authentication: Bearer token in Authorization header
   - Event format: `event: state`, `data: {"accountId": {"TypeName": "newStateString"}}`
   - The `types` parameter filters which JMAP types trigger events (Email, Mailbox, Thread, etc.)
   - `closeafter=state` mode: server closes after first event (useful for long-polling pattern)
   - `closeafter=no` mode: persistent connection with keepalive pings
   - Reconnection: SSE spec says client should reconnect on disconnect; server may send `retry:` field

3. **Fastmail-Specific Observations** (from running the discovery script and from the session endpoint):
   - EventSource URL: `https://api.fastmail.com/jmap/event/`
   - Note which JMAP types Fastmail sends events for (Email, Mailbox, Thread, etc.)
   - Note: Document that the executor should run test_14 and paste observed output into this section, adding concrete observations about event frequency, payload examples, and which actions trigger which type changes.
   - Add placeholder sections with clear instructions: "Run `python human-tests/test_14_eventsource.py --duration 120` while performing these actions, then fill in observations: (a) send yourself an email, (b) apply a triage label, (c) move an email between folders"

4. **Implications for Push Architecture**:
   - Current polling approach: `ScreenerWorkflow.poll()` runs every N seconds
   - Push approach: Listen for EventSource `state` events where `Email` or `Mailbox` state changes, then trigger a triage pass
   - Debounce consideration: Multiple rapid state changes (e.g., batch email arrival) should be collapsed into a single triage pass. Document that the discovery script's output will reveal natural event clustering patterns.
   - Reconnection strategy: What happens when SSE connection drops? Need exponential backoff with fallback to polling.
   - Hybrid approach: Use EventSource as primary trigger, keep polling as fallback safety net (e.g., poll every 5 minutes even with active SSE to catch any missed events)

5. **Open Questions** (to be answered after running discovery script):
   - How quickly do events fire after an email arrives?
   - Do label changes trigger separate events from email state changes?
   - What is the practical minimum debounce window?
   - Does Fastmail rate-limit EventSource connections?

6. **References**:
   - RFC 8620 section 7.3: https://www.rfc-editor.org/rfc/rfc8620#section-7.3
   - Related todo: `.planning/todos/pending/2026-02-25-replace-polling-with-jmap-eventsource-push-and-debouncer.md`
  </action>
  <verify>
    test -f .research/jmap-eventsource.md && wc -l .research/jmap-eventsource.md | awk '{if ($1 >= 40) print "PASS: " $1 " lines"; else print "FAIL: only " $1 " lines"}'
  </verify>
  <done>Research document exists with spec details, Fastmail observations section (with placeholders for empirical data), push architecture implications, debounce considerations, and open questions for discovery</done>
</task>

</tasks>

<verification>
1. `python human-tests/test_14_eventsource.py --duration 10` runs without errors, connects to EventSource, and exits cleanly
2. `.research/jmap-eventsource.md` exists with structured sections covering spec, observations, and architecture implications
3. No new dependencies added to pyproject.toml (uses only httpx which is already installed)
</verification>

<success_criteria>
- test_14_eventsource.py successfully connects to Fastmail's JMAP EventSource endpoint
- SSE events are parsed and displayed with timestamps and structured payloads
- Script handles both --duration timeout and Ctrl+C gracefully with summary output
- Research document captures RFC 8620 section 7.3 spec details and push architecture implications
- No new dependencies required (httpx streaming handles SSE natively)
</success_criteria>

<output>
After completion, create `.planning/quick/4-create-jmap-eventsource-discovery-script/4-SUMMARY.md`
</output>
