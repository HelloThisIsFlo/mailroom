# Domain Pitfalls: v1.1 Push, Configurable Categories, and Setup Script

**Domain:** Adding JMAP EventSource push, configurable triage categories, and Fastmail setup script to an existing email triage service
**Researched:** 2026-02-25
**Confidence:** MEDIUM-HIGH (codebase fully inspected, RFC 8620 EventSource spec verified, Fastmail SSE behavior empirically tested, pydantic-settings docs verified; SSE long-lived behavior in production not yet validated)

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or service outages.

---

### Pitfall 1: SSE Silent Death -- Connection Alive but No Events Delivered

**What goes wrong:**
The EventSource SSE connection appears healthy (no exception thrown, TCP socket open) but stops delivering events. This is the most dangerous SSE failure mode because the code thinks it is listening when it is actually deaf. The service degrades to no-push without anyone noticing -- triage latency silently jumps from ~5 seconds back to 5 minutes, and if polling fallback is broken or removed, triage stops entirely.

**Why it happens:**
Three root causes, all documented in production SSE deployments:
1. **Intermediary buffering:** Proxies, load balancers, or network middleboxes between the pod and Fastmail buffer SSE data and never forward it. The TCP connection is alive but the application receives nothing. This is especially common with HTTP/1.1 connections through corporate/cloud proxies.
2. **TCP half-open state:** The remote end (Fastmail) closes the connection, but the local TCP stack does not detect it because no data is being sent from the client side. The `iter_lines()` call blocks forever, waiting for data on a dead socket.
3. **Fastmail server-side timeout:** Fastmail may silently close idle EventSource connections. The discovery script observed 30-second keepalive pings, but the server's maximum idle tolerance is undocumented. If pings stop and the client does not detect this, the connection is dead.

**Consequences:**
- Service appears healthy (health endpoint reports based on last successful poll, not SSE state)
- If the fallback poll timer was accidentally broken during SSE integration, triage stops completely
- If the fallback is working, service silently degrades to 5-minute polling -- user notices "it used to be instant"

**Prevention:**
1. **Ping-based liveness detection:** Track the timestamp of the last received SSE line (data, comment, or ping). If no line arrives within `2 * ping_interval` (e.g., 60 seconds when ping=30), declare the connection dead and force reconnect. This is the integration sketch's `read=300.0` timeout, but 300 seconds is far too generous -- a 60-second timeout catches dead connections 5 minutes sooner.
2. **Never remove polling fallback:** The fallback poll timer in the main loop is the safety net. The SSE listener is an optimization, not a replacement. Design the main loop so polling cannot be accidentally disabled.
3. **Log SSE health state:** Log `eventsource_alive` periodically (every 5 minutes) with a counter of events received since last log. This makes silent death visible in logs.
4. **Health endpoint should report SSE status:** Extend the `/healthz` response to include `"eventsource_connected": true/false` and `"last_sse_event_age_seconds": N`. Operators can alert on SSE staleness independent of poll health.

**Detection:**
- No `eventsource_alive` log entries for extended periods
- Health endpoint shows `last_sse_event_age_seconds` > 120 while emails are arriving
- Triage latency regression visible in logs (poll_complete events with triaged_senders > 0 always appearing at 300-second intervals, never at 3-5 second intervals)

**Phase to address:** EventSource phase -- build liveness detection into the SSE listener from day one, not as a follow-up.

---

### Pitfall 2: Config Migration Breaks 180 Existing Tests

**What goes wrong:**
Replacing the current flat `label_to_imbox`/`group_imbox` config fields with a new configurable categories structure (list of mappings) breaks every test that constructs `MailroomSettings` with the current env vars. The 180 unit tests and 13 human tests all depend on the current config shape: `MAILROOM_LABEL_TO_IMBOX`, `MAILROOM_GROUP_IMBOX`, etc. A structural config change means every `monkeypatch.setenv` call in every test file that touches config needs updating, plus the k8s ConfigMap, the `.env.example`, and the deployment docs.

**Why it happens:**
The todo says "replace the current hardcoded `label_to_paper_trail` / `group_paper_trail` pattern with a dynamic list." This implies a breaking change to the config schema. The current config has 18+ individual env vars consumed by the k8s ConfigMap. Changing these to a single JSON env var (`MAILROOM_TRIAGE_CATEGORIES='[{"label": "@ToImbox", "group": "Imbox", ...}]'`) is a fundamentally different shape.

**Consequences:**
- Mass test breakage during migration (friction slows development, risk of introducing test gaps)
- Existing k8s deployment stops working until ConfigMap is updated
- Human tests that rely on config defaults stop working
- If backward compatibility is not maintained, there is no safe rollback path

**Prevention:**
1. **Backward-compatible migration:** Keep ALL existing flat env vars working as defaults. Add the new `triage_categories` field as an OPTIONAL override. When `triage_categories` is set, it takes precedence; when absent, the system constructs categories from the existing flat fields. This means zero tests break and zero k8s manifests change.
2. **Deprecation, not removal:** Mark the flat fields as deprecated in comments/docs but do not remove them in v1.1. Remove them in v1.2 after the new config is proven.
3. **Property bridge:** The existing `label_to_group_mapping`, `triage_labels`, `contact_groups`, and `required_mailboxes` properties are the API surface the workflow consumes. Keep these properties, just change their internal implementation to derive from either the new categories list or the legacy flat fields.
4. **Test the migration path itself:** Add a test that constructs config from both the old flat vars AND the new categories format, verifying they produce identical `label_to_group_mapping` output.

**Detection:**
- Running `pytest` early in the config phase catches breakage immediately
- Any config change that requires touching `test_config.py` AND `test_screener_workflow.py` AND `conftest.py` is a sign the change is too broad

**Phase to address:** Configurable categories phase -- design backward-compatible migration before writing any config code.

---

### Pitfall 3: SSE Reconnection Thundering Herd with Polling

**What goes wrong:**
When the SSE connection drops and reconnects, it receives an initial `type: "connect"` event containing current state. This triggers a triage pass. But the fallback poll timer may also fire during or immediately after the reconnection window, causing two near-simultaneous `workflow.poll()` calls. If the debounce logic does not account for reconnection events, the service processes the same batch of triaged emails twice. While the system is idempotent (contact upsert is safe, label removal is safe), it wastes API calls and produces confusing duplicate log entries.

**Why it happens:**
The integration sketch's debounce logic handles rapid event bursts correctly but does not distinguish between reconnection initial-state events and genuine change events. Both put `"state_changed"` on the queue. After a disconnect lasting several minutes, the fallback poll may have already processed the batch, and the SSE reconnect triggers a redundant second pass.

**Consequences:**
- Doubled API calls to Fastmail (JMAP queries + CardDAV lookups) for the same batch
- Duplicate log entries for the same triage actions (confusing for debugging)
- In extreme cases, rapid reconnect/disconnect cycling could cause repeated processing

**Prevention:**
1. **Debounce window covers reconnection:** After SSE reconnection, apply a longer debounce (e.g., 10 seconds instead of 3) to allow the fallback poll to complete first if it was already in progress.
2. **Poll-in-progress guard:** Add a simple boolean flag that prevents `workflow.poll()` from being called while a previous poll is still running. The main thread already does this naturally (sequential execution), but the debounce window after reconnect should account for the most recent poll timestamp.
3. **Skip if recently polled:** Before triggering a poll from SSE, check if a poll completed within the last N seconds (e.g., 10). If so, skip. This is the simplest and most robust approach.

**Detection:**
- Log entries showing two `poll_complete` events within seconds of each other
- High API call volume during SSE reconnection periods

**Phase to address:** EventSource phase -- the "skip if recently polled" guard should be part of the debounce implementation.

---

### Pitfall 4: Setup Script Creates Labels but Fastmail Rules Do Not Exist

**What goes wrong:**
The setup script creates mailboxes (labels like `@ToImbox`, `@ToFeed`) and contact groups (`Imbox`, `Feed`, `Paper Trail`, `Jail`) on Fastmail. The user runs it, sees success, deploys Mailroom, and triages a sender. Mailroom correctly adds the contact to the `Feed` group and sweeps their emails out of Screener. But future emails from that sender still arrive in Screener instead of Feed, because **Fastmail sieve rules that route emails based on contact group membership do not exist yet.** The setup script cannot create sieve rules via JMAP or CardDAV -- there is no API for it.

**Why it happens:**
Mailroom's entire architecture assumes that Fastmail sieve rules handle future email routing. The triage action (adding a contact to a group) only affects the current backlog. Future routing depends on rules like "If sender is in Feed group, deliver to Feed mailbox." These rules must be created manually in Fastmail Settings > Filters & Rules. The setup script creates the prerequisite infrastructure (labels and groups) but cannot create the rules that make them useful.

**Consequences:**
- User thinks setup is complete, but the core value proposition (future emails auto-routed) does not work
- Triaged senders' new emails keep landing in Screener, making it seem like Mailroom is broken
- User may re-triage the same sender repeatedly, wondering why it does not "stick"

**Prevention:**
1. **Setup script MUST output human instructions:** After creating labels and groups, print step-by-step instructions for creating the required sieve rules. Include the exact rule conditions and actions.
2. **Validation step:** Add a `--verify` flag to the setup script that checks whether rules exist by testing the routing behavior: send a test email from a known contact in a group and verify it arrives in the correct mailbox. This is complex but valuable.
3. **Document the gap prominently:** The setup script's output and Mailroom's README must make it crystal clear that sieve rules are a manual step. Do not bury this in a footnote.
4. **Post-setup checklist:** The script should output a numbered checklist: "1. Labels created (done). 2. Groups created (done). 3. Sieve rules -- YOU MUST CREATE THESE MANUALLY (instructions below)."

**Detection:**
- New triaged senders' emails continue arriving in Screener after triage
- User reports that Mailroom "works once but not for future emails"

**Phase to address:** Setup script phase -- the script must be designed with the sieve rule gap as a first-class concern, not an afterthought.

---

## Moderate Pitfalls

Mistakes that cause significant debugging time, degraded functionality, or require non-trivial fixes.

---

### Pitfall 5: pydantic-settings JSON-in-Env-Var Ergonomics Disaster

**What goes wrong:**
The configurable categories feature requires a list of structured objects. The natural pydantic-settings approach is a single env var with a JSON array:

```
MAILROOM_TRIAGE_CATEGORIES='[{"label":"@ToBillboard","group":"Billboard","destination_mailbox":"Paper Trail","contact_type":"company"}]'
```

This works technically, but it is a terrible user experience for k8s ConfigMap management. The ConfigMap YAML requires escaping the JSON, and editing it requires getting the JSON exactly right with no validation feedback until the pod crashes at startup. Multi-line JSON in a ConfigMap `data` field is fragile and error-prone.

**Why it happens:**
pydantic-settings handles complex types by parsing JSON from env vars. This is documented and works. But k8s ConfigMaps are designed for simple key-value pairs. Stuffing JSON into a ConfigMap value fights the tool's ergonomics.

**Prevention:**
1. **Support both formats:** Accept JSON in a single env var for advanced users, but ALSO support the existing flat env var pattern for simple cases. The backward-compatible approach from Pitfall 2 already achieves this.
2. **Config file source:** For complex category configurations, support loading from a JSON or YAML file mounted as a ConfigMap volume. pydantic-settings supports custom sources -- add a file-based source that reads `/config/categories.yaml` if it exists. This is the standard k8s pattern for structured config.
3. **Validation with clear errors:** If JSON parsing fails, the error message must say exactly what is wrong with the JSON, not just "validation error for field triage_categories." Add a custom validator that catches `json.JSONDecodeError` and re-raises with a helpful message.
4. **Default categories in code:** Ship the current 5 categories (Imbox, Feed, Paper Trail, Jail, Person) as the default. Users who want the same setup as v1.0 change nothing. Users who want to add Billboard just add one entry to the list.

**Detection:**
- User struggles to edit ConfigMap and asks for help
- Pod crash loops with opaque pydantic validation errors

**Phase to address:** Configurable categories phase -- design the config input format before implementing the data model.

---

### Pitfall 6: SSE Thread Death Kills Push Without Killing Service

**What goes wrong:**
The SSE listener thread crashes with an unhandled exception (e.g., `httpx.RemoteProtocolError` from a malformed SSE frame). Because the thread is a daemon thread, Python does not propagate the exception to the main thread. The main loop continues running with only the fallback poll timer. The service appears healthy (polls still succeed, health endpoint reports OK), but push notifications are silently gone.

**Why it happens:**
The integration sketch marks the SSE thread as `daemon=True`, which means it exits silently when it crashes. The reconnection logic (`while not shutdown_event.is_set()`) catches `Exception` broadly, but specific exception types from httpx (like `httpx.RemoteProtocolError`, `httpx.StreamError`) might not be caught cleanly, or the reconnect delay logic might have a bug that causes it to exit the loop.

**Consequences:**
- Push latency silently degrades to polling-only
- Logs may show a single `eventsource_disconnected` warning, then silence -- easy to miss
- Service stays "healthy" by all standard measures

**Prevention:**
1. **Thread health monitoring:** The main loop should check the SSE thread's `is_alive()` state periodically (e.g., once per poll cycle). If the thread is dead, restart it and log a warning.
2. **Wrap the entire listener in a catch-all:** The outermost loop in the SSE listener must catch `BaseException` (not just `Exception`), log it, and continue the reconnection loop. Only `shutdown_event.is_set()` should cause the thread to exit.
3. **Health endpoint reports thread state:** Add `"eventsource_thread_alive": true/false` to the health response. Kubernetes can alert on this.
4. **Never fail silently:** Every time the SSE listener restarts its connection, log it at WARNING level. Every time the thread catches an exception, log the full traceback.

**Detection:**
- Health endpoint shows `eventsource_thread_alive: false`
- No `eventsource_connected` log entries for extended periods
- Main loop log shows only `poll_complete` events at 300-second intervals

**Phase to address:** EventSource phase -- thread monitoring belongs in the main loop, implemented alongside the SSE listener.

---

### Pitfall 7: Setup Script Idempotency Failure on Partial Runs

**What goes wrong:**
The setup script creates labels and contact groups in separate steps. If it successfully creates labels but crashes before creating groups (e.g., CardDAV auth fails), re-running the script tries to create the labels again. If the create logic uses `Mailbox/set` with `create` and the mailbox already exists, Fastmail may reject it or create a duplicate mailbox with the same name (JMAP allows sibling mailboxes with different parents to have the same name, and implementation behavior varies).

**Why it happens:**
JMAP `Mailbox/set` `create` does not have built-in "create if not exists" semantics. If you call create with a name that already exists at the same parent level, the spec says "There MUST NOT be two sibling Mailboxes with both the same parent and the same name" -- so the server SHOULD reject it, but the error response format varies and may not be obvious. Contact groups have the same issue: creating a group vCard with the same `FN` as an existing group creates a duplicate group.

**Consequences:**
- Duplicate labels or groups in Fastmail
- Mailroom startup fails because `resolve_mailboxes()` finds ambiguous name matches
- User has to manually clean up duplicates in Fastmail UI

**Prevention:**
1. **Check-then-create pattern:** Before creating any resource, query for its existence. For mailboxes: `Mailbox/get` + filter by name. For groups: fetch address book + filter for `KIND:group` with matching `FN`. Only create what is missing.
2. **Report what exists vs. what was created:** The script output should clearly distinguish "Created @ToImbox" from "Skipped @ToImbox (already exists)". This gives the user confidence in re-running.
3. **Transactional ordering:** Create groups first, then labels. Groups are the harder resource to validate (CardDAV vs JMAP). If group creation fails, no labels are created, keeping the system in a clean state for retry.
4. **Test with live Fastmail:** Mailbox name uniqueness enforcement is implementation-specific. Test that Fastmail rejects or handles duplicate mailbox creation at the same parent level before relying on it.

**Detection:**
- `resolve_mailboxes()` at startup finds multiple mailboxes with the same name
- Fastmail UI shows duplicate labels or groups
- Setup script output shows creation of resources that should already exist

**Phase to address:** Setup script phase -- idempotency is a core design requirement, not an enhancement.

---

### Pitfall 8: httpx Streaming Timeout Configuration Wrong for SSE

**What goes wrong:**
The `httpx.Client` timeout defaults (`read=5.0s`) immediately kill the SSE connection because SSE involves long periods of no data between events. The integration sketch sets `read=300.0`, but this is a hard timeout on the entire read operation, not an idle timeout. If Fastmail's 30-second keepalive pings stop (server issue), the client waits 5 full minutes before detecting the failure. Conversely, if `pool` timeout is too short, httpx may close the connection pool and kill the SSE connection during normal idle periods.

**Why it happens:**
httpx's `Timeout` object has four settings: `connect`, `read`, `write`, `pool`. For SSE, `read` must be long enough to wait for the next event or ping, but short enough to detect connection death. This is a fundamental tension in SSE with timeout-based clients.

**Consequences:**
- `read` too short: connection constantly drops and reconnects, causing event storms
- `read` too long: dead connections take minutes to detect
- `pool` too short: connection pool cleanup kills the SSE stream

**Prevention:**
1. **Set read timeout to 2x ping interval:** With `ping=30`, use `read=65.0` (30s ping + 30s tolerance + 5s buffer). This detects dead connections within ~65 seconds while surviving normal ping gaps.
2. **Disable pool timeout:** Set `pool=None` for the SSE-specific httpx client. The SSE connection should never be returned to a pool.
3. **Use a separate httpx client for SSE:** Do not share the JMAP API client (which has normal timeouts) with the SSE listener. Create a dedicated client with SSE-appropriate timeout configuration.
4. **Handle `httpx.ReadTimeout` explicitly:** In the SSE listener, catch `ReadTimeout` and treat it as "connection dead, reconnect" -- not as a fatal error.

**Detection:**
- Frequent `eventsource_disconnected` + `eventsource_connected` log pairs (timeout too short)
- Long gaps between SSE disconnection and reconnection (timeout too long)
- `ReadTimeout` exceptions in SSE listener logs

**Phase to address:** EventSource phase -- timeout configuration is part of SSE client setup, not a tuning afterthought.

---

### Pitfall 9: New Categories Not Reflected in required_mailboxes/contact_groups

**What goes wrong:**
A user adds a new triage category (e.g., `@ToBillboard` -> `Billboard` group -> `Paper Trail` mailbox) to the config. The category is parsed correctly and appears in `label_to_group_mapping`. But on startup, `required_mailboxes` and `contact_groups` still only return the hardcoded set from the flat config fields. The service does not validate that `@ToBillboard` exists as a Fastmail mailbox or that `Billboard` exists as a contact group. It crashes at runtime when the first `@ToBillboard` email is processed, with a `KeyError` in `_mailbox_ids`.

**Why it happens:**
The current `required_mailboxes` and `contact_groups` properties are derived from the flat config fields:

```python
@property
def contact_groups(self) -> list[str]:
    return [self.group_imbox, self.group_feed, self.group_paper_trail, self.group_jail]
```

If the configurable categories feature adds new categories to `label_to_group_mapping` but does not also update `required_mailboxes` and `contact_groups` to include the new entries, startup validation misses them.

**Consequences:**
- New categories appear to work (config loads) but crash at runtime
- The crash only happens when a user actually applies the new label, which could be days after deployment
- Startup validation gives false confidence ("all checks passed")

**Prevention:**
1. **Derive ALL validation lists from the mapping:** `required_mailboxes` and `contact_groups` must be computed from `label_to_group_mapping`, not from individual fields. This is already partially done (destinations are extracted from the mapping in `required_mailboxes`), but `contact_groups` is not.
2. **Test with a custom category:** Add a test that configures an extra category and verifies it appears in `required_mailboxes`, `contact_groups`, and `triage_labels`. This test would have caught the bug.
3. **Startup integration test:** Add a human test that configures a custom category, starts the service, and verifies it validates the category's label and group exist.

**Detection:**
- `KeyError` in `_mailbox_ids` when processing a custom category
- Custom category works in config but fails at triage time
- `contact_groups` property returns fewer groups than `label_to_group_mapping` references

**Phase to address:** Configurable categories phase -- the derived properties must be updated as part of the config change, verified by tests.

---

## Minor Pitfalls

Issues that cause friction, confusion, or minor bugs but have straightforward fixes.

---

### Pitfall 10: SSE Debounce Window Too Short for Label Application

**What goes wrong:**
User applies a triage label to an email in Fastmail. This generates a Mailbox state change event (SSE fires). Mailroom debounces for 3 seconds and triggers a poll. But the JMAP state on Fastmail's backend has not fully propagated yet -- the `Email/query` call returns the email in the triage mailbox, but the `Email/get` for sender details might fail or return stale data because Fastmail's internal replication has a brief lag.

**Why it happens:**
Fastmail's SSE events fire when state strings change, not when the underlying data is fully consistent across all JMAP methods. The gap is typically sub-second, but under load it could be longer. A 3-second debounce is probably sufficient, but this is an empirical question that the EventSource research document flagged as needing measurement.

**Prevention:**
1. **Make debounce configurable:** The integration sketch already suggests `MAILROOM_DEBOUNCE_SECONDS=3`. Leave this configurable so it can be tuned based on empirical observation.
2. **Handle "triage label found but email metadata incomplete" gracefully:** If `get_email_senders` returns no sender for an email that was just labeled, log it and leave the label for next poll. The existing retry logic handles this.
3. **Run empirical tests with the discovery script:** Before choosing the final debounce value, run the discovery script during real triage operations and measure the gap between "event received" and "data queryable."

**Detection:**
- Log entries showing `email_missing_sender` immediately after SSE-triggered polls, but not during fallback polls
- Intermittent `sender_processing_failed` errors that resolve on the next poll

**Phase to address:** EventSource phase -- configurable debounce with empirical tuning.

---

### Pitfall 11: Setup Script Cannot Determine Mailbox Hierarchy for Custom Categories

**What goes wrong:**
A user configures a custom category with `destination_mailbox: "Paper Trail/Billboard"` (a child mailbox under Paper Trail). The setup script needs to create the "Billboard" mailbox as a child of "Paper Trail." But to do this, it needs the parent mailbox's ID. If "Paper Trail" does not exist yet (first-time setup), it must be created first, then its ID used as `parentId` for "Billboard." The script must handle arbitrary nesting depth and creation order dependencies.

**Why it happens:**
JMAP `Mailbox/set` create requires `parentId` for child mailboxes, but the parent must already exist. If creating multiple levels of hierarchy in one JMAP request, you need to use back-references (`#id_ref`) to reference the just-created parent. This is technically possible in JMAP but adds significant complexity to the setup script.

**Prevention:**
1. **Flat namespace for v1.1:** Do not support nested categories in v1.1. Require all destination mailboxes to be top-level. This eliminates the hierarchy problem entirely. Add hierarchy support in v1.2 if users actually need it.
2. **If hierarchy is needed:** Sort creation by depth (parents before children). Use JMAP back-references within a single `Mailbox/set` call to create parent and child atomically. Fall back to sequential creation if back-references are not supported.
3. **Validate hierarchy in config:** If a category references a nested mailbox (contains `/`), validate that this is supported and the parent is either an existing mailbox or another category in the config.

**Detection:**
- Setup script fails with "parent mailbox not found" when creating child mailboxes
- User configures nested categories but setup script creates flat mailboxes

**Phase to address:** Configurable categories phase (design) and setup script phase (implementation). Decide hierarchy scope early.

---

### Pitfall 12: @ToPerson Becomes Ambiguous with Custom Categories

**What goes wrong:**
The current `@ToPerson` label is a modifier: it routes to the same destination as `@ToImbox` but creates a person-type contact instead of a company-type contact. With configurable categories, users might expect `@ToPerson` to work as a modifier for ANY category (e.g., `@ToPerson` + `@ToBillboard` should create a person contact in Billboard). But the current implementation hardcodes `@ToPerson` as routing to Imbox. The interaction between `@ToPerson` and custom categories is undefined.

**Why it happens:**
`@ToPerson` was designed for the fixed 4-category system. It is mapped in `label_to_group_mapping` as a fifth entry pointing to the Imbox group. With configurable categories, the concept of "person modifier" does not fit neatly into the "one label -> one destination" model.

**Prevention:**
1. **Keep @ToPerson as-is for v1.1:** It routes to Imbox as a person contact. Custom categories always create company contacts. This is the simplest and least disruptive approach.
2. **Document the limitation:** Make it clear that `@ToPerson` only applies to Imbox triage, not custom categories.
3. **Future design:** In v1.2, consider making `contact_type` a configurable field per category. Users who want a "person" version of Billboard can create a `@ToBillboardPerson` category with `contact_type: "person"`.

**Detection:**
- User applies `@ToPerson` and `@ToBillboard` to same email, expecting person-type Billboard contact
- Conflict detection fires because two labels are on the same email

**Phase to address:** Configurable categories phase -- document the @ToPerson scope clearly in the config schema.

---

### Pitfall 13: Setup Script Runs with Wrong Credentials

**What goes wrong:**
The setup script creates JMAP mailboxes (using the JMAP token) and CardDAV contact groups (using the CardDAV username/password). If the user runs the script with credentials for a different Fastmail account (e.g., their test account), it creates labels and groups on the wrong account. Mailroom then starts with production credentials and fails validation because the labels and groups do not exist on the production account.

**Why it happens:**
The script reads from the same `.env` file or env vars as the main service. If the user has multiple `.env` files or has not updated their env vars after switching accounts, the credentials mismatch is silent.

**Prevention:**
1. **Print the account being configured:** At the start of the script, print "Configuring Fastmail account: user@fastmail.com" (from the CardDAV username) and "JMAP account ID: u5bde4052" (from the session). Ask for confirmation before proceeding.
2. **Dry-run by default:** The first run should be `--dry-run`, printing what WOULD be created without creating it. Require `--apply` to actually make changes. This gives the user a chance to verify the target account.
3. **Compare JMAP and CardDAV accounts:** Verify that the JMAP token's account and the CardDAV username refer to the same Fastmail account. If they do not match, warn loudly.

**Detection:**
- Setup script succeeds but Mailroom startup fails with "required mailboxes not found"
- Labels/groups appear on the wrong Fastmail account

**Phase to address:** Setup script phase -- account verification is part of the script's startup sequence.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| EventSource SSE listener | Silent connection death (Pitfall 1) | Ping-based liveness detection with 60s timeout; never remove polling fallback |
| EventSource SSE listener | Thread crash kills push silently (Pitfall 6) | Main loop monitors thread health; catch-all exception handler in thread |
| EventSource SSE listener | httpx timeout misconfiguration (Pitfall 8) | Dedicated httpx client for SSE with read=65s, pool=None |
| EventSource debounce | Reconnection thundering herd (Pitfall 3) | "Skip if recently polled" guard before triggering poll |
| EventSource debounce | Debounce too short for Fastmail propagation (Pitfall 10) | Configurable debounce; empirical measurement before shipping |
| Configurable categories config | 180 tests break from config migration (Pitfall 2) | Backward-compatible: new field optional, old fields still work |
| Configurable categories config | JSON-in-env-var ergonomics (Pitfall 5) | Support both JSON env var and config file; ship with sensible defaults |
| Configurable categories config | Derived properties miss new categories (Pitfall 9) | Compute all validation lists from the mapping, not from individual fields |
| Configurable categories config | @ToPerson ambiguity with custom categories (Pitfall 12) | Keep @ToPerson scoped to Imbox; document limitation |
| Setup script provisioning | Sieve rules cannot be created by script (Pitfall 4) | Print human instructions for rules; post-setup checklist |
| Setup script provisioning | Idempotency failure on partial runs (Pitfall 7) | Check-then-create pattern; report exists vs. created |
| Setup script provisioning | Mailbox hierarchy complexity (Pitfall 11) | Flat namespace only in v1.1; defer hierarchy to v1.2 |
| Setup script provisioning | Wrong account credentials (Pitfall 13) | Print account info; dry-run by default; require --apply |

## "Looks Done But Isn't" Checklist for v1.1

- [ ] **SSE liveness monitoring:** Does the SSE listener detect and recover from silent connection death within 60 seconds? (Not just "does it reconnect on exception")
- [ ] **SSE thread restart:** If the SSE thread crashes, does the main loop notice and restart it? Test by injecting an exception in the listener.
- [ ] **Fallback poll still works:** With SSE enabled, does the 5-minute fallback poll still trigger if no SSE events arrive? Test by blocking the SSE endpoint.
- [ ] **Config backward compatibility:** Do ALL 180 existing tests pass with zero changes after adding configurable categories? Test by running `pytest` before touching any test files.
- [ ] **Custom category startup validation:** Does adding a custom category to config cause `required_mailboxes` and `contact_groups` to include the new entries? Test with a category that references a non-existent mailbox.
- [ ] **Setup script idempotency:** Running the setup script twice produces the same result as running it once. No duplicate labels or groups.
- [ ] **Setup script sieve rule guidance:** Does the setup script output include clear instructions for creating sieve rules? Would a new user know what to do?
- [ ] **Health endpoint reports SSE state:** Does `/healthz` include `eventsource_connected` and `eventsource_thread_alive` fields?
- [ ] **Human test for SSE:** Is there a `test_15_eventsource_push.py` that verifies SSE events trigger a triage pass?
- [ ] **Human test for custom category:** Is there a human test that configures a custom category and verifies end-to-end triage?

## Sources

- [RFC 8620 Section 7.3: Event Source](https://www.rfc-editor.org/rfc/rfc8620#section-7.3) -- JMAP EventSource specification (HIGH confidence)
- [JMAP Mail Specification (RFC 8621)](https://jmap.io/spec-mail.html) -- Mailbox/set create properties and restrictions (HIGH confidence)
- [SSE production issues: "Server Sent Events are still not production ready after a decade"](https://dev.to/miketalbot/server-sent-events-are-still-not-production-ready-after-a-decade-a-lesson-for-me-a-warning-for-you-2gie) -- Real-world SSE pitfalls: proxy buffering, connection drops, silent failures (MEDIUM confidence)
- [pydantic-settings: Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- JSON env var parsing, nested delimiter, complex types (HIGH confidence)
- [pydantic/pydantic-settings#203: Deeply nested settings overrides](https://github.com/pydantic/pydantic-settings/issues/203) -- Known limitations with nested models (MEDIUM confidence)
- [Kubernetes ConfigMaps documentation](https://kubernetes.io/docs/concepts/configuration/configmap/) -- ConfigMap ergonomics and file-based config patterns (HIGH confidence)
- [SSE connection timeout: seqeralabs/nf-tower#48](https://github.com/seqeralabs/nf-tower/issues/48) -- SSE idle connection resets at 5 minutes (MEDIUM confidence)
- [W3C Server-Sent Events specification](https://html.spec.whatwg.org/multipage/server-sent-events.html) -- Keepalive comment convention (HIGH confidence)
- [TCP half-open connection detection](https://blog.stephencleary.com/2009/05/detection-of-half-open-dropped.html) -- Why TCP connections can appear alive when dead (HIGH confidence)
- Mailroom codebase: `src/mailroom/` (directly inspected), `tests/`, `human-tests/`, `k8s/` -- current implementation details (HIGH confidence)
- Mailroom EventSource research: `.research/jmap-eventsource/` -- Fastmail SSE behavior observations and integration sketch (HIGH confidence)
- [httpx-sse PyPI](https://pypi.org/project/httpx-sse/) -- httpx SSE library exists but manual parsing is already implemented (MEDIUM confidence)

---
*Pitfalls research for: v1.1 Push, Configurable Categories, and Setup Script*
*Researched: 2026-02-25*
