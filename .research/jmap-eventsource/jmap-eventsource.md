# JMAP EventSource Research

Research document for understanding Fastmail's JMAP EventSource (Server-Sent Events) push notifications, informing future push-based architecture for Mailroom.

## Overview

JMAP EventSource is defined in [RFC 8620 section 7.3](https://www.rfc-editor.org/rfc/rfc8620#section-7.3) as the standard mechanism for servers to push state change notifications to clients. It uses the W3C Server-Sent Events (SSE) protocol over HTTP, allowing a persistent connection where the server sends events as they occur.

**Why this matters for Mailroom:** The current `ScreenerWorkflow.poll()` runs every N seconds regardless of whether new emails have arrived. EventSource enables a push model where Mailroom only triggers a triage pass when state actually changes -- reducing API calls, latency, and unnecessary work.

## Spec Details (RFC 8620 Section 7.3)

### URL Format

```
GET {eventSourceUrl}?types={types}&closeafter={state|no}&ping={seconds}
```

The `eventSourceUrl` is discovered from the JMAP session resource (`/jmap/session`).

### Query Parameters

| Parameter    | Values              | Description                                           |
|-------------|---------------------|-------------------------------------------------------|
| `types`     | Comma-separated or `*` | JMAP type names to subscribe to (e.g., `Email,Mailbox`) or `*` for all |
| `closeafter`| `state` or `no`     | `state`: server closes after first event (long-poll). `no`: persistent connection |
| `ping`      | Positive integer    | Seconds between keepalive pings from server            |

### Authentication

Standard JMAP bearer token in the Authorization header:
```
Authorization: Bearer {token}
Accept: text/event-stream
```

### SSE Event Format

Events follow the W3C Server-Sent Events specification:

```
event: state
data: {"accountId": {"TypeName": "newStateString", ...}}
```

- `event:` line specifies the event type (always `state` for JMAP)
- `data:` line contains JSON payload mapping account IDs to changed type states
- `:` lines are comments / keepalive pings
- Empty lines delimit events
- `retry:` lines suggest reconnection interval in milliseconds

### Connection Modes

**Persistent (`closeafter=no`):** Server keeps connection open indefinitely, sending `state` events as changes occur and keepalive pings at the specified interval. Ideal for long-running daemons.

**Long-poll (`closeafter=state`):** Server closes connection after the first state event. Client reconnects to wait for the next change. Simpler but more HTTP overhead.

## Fastmail-Specific Observations

### Session Discovery

The Fastmail session endpoint (`https://api.fastmail.com/jmap/session`) includes:
```json
{
  "eventSourceUrl": "https://api.fastmail.com/jmap/event/"
}
```

### Event Envelope Format

Fastmail wraps the RFC 8620 state data in an envelope:
```json
{
  "changed": {
    "u5bde4052": {
      "ContactCard": "84576",
      "Mailbox": "J84602",
      "AddressBook": "48",
      "Email": "J84602",
      "EmailDelivery": "J84602",
      "Thread": "J84602"
    }
  },
  "type": "connect"
}
```

Top-level keys:
- `changed` -- maps account IDs to type-state pairs (the RFC 8620 payload)
- `type` -- Fastmail extension: `connect` (initial state on connection), `change` (subsequent updates)

### Observed JMAP Types

On initial connection, Fastmail reports state for these types:
- **Email** -- email message state
- **EmailDelivery** -- email delivery state
- **Mailbox** -- mailbox/label state
- **Thread** -- conversation thread state
- **ContactCard** -- contact card state
- **AddressBook** -- address book state

### Empirical Observations (To Be Completed)

> **Instructions:** Run the discovery script while performing actions in Fastmail to populate this section with real observations.
>
> ```bash
> python .research/jmap-eventsource/eventsource_discovery.py --duration 120
> ```
>
> While the script is running, perform these actions and note which events fire:
>
> 1. **Send yourself an email** -- Which types change? How quickly does the event fire?
> 2. **Apply a triage label** (e.g., @ToImbox) -- Does this trigger a separate Mailbox event?
> 3. **Move an email between folders** -- What types change?
> 4. **Edit a contact** -- Does ContactCard state change?
>
> Record: event type, changed types, timing relative to action, any clustering patterns.

#### Placeholder: Event Frequency

- Time from action to event: _[to be measured]_
- Events per email arrival: _[to be measured]_
- Debounce natural window: _[to be measured]_

#### Placeholder: Event Clustering

- Do batch arrivals produce one event or many? _[to be observed]_
- Do label changes produce events separate from email state? _[to be observed]_

## Implications for Push Architecture

### Current Approach

`ScreenerWorkflow.poll()` runs on a fixed interval (default: 300s / 5 minutes). Every poll:
1. Queries the Screener mailbox for emails
2. For each unique sender, looks up triage labels
3. Processes labeled senders (move emails, create contacts)

This works but has inherent latency (up to 5 minutes) and makes unnecessary API calls when nothing has changed.

### Proposed Push Approach

Listen for EventSource `state` events where `Email`, `Mailbox`, or `EmailDelivery` state changes, then trigger a triage pass:

```
EventSource "state" event
  -> Filter: Email or Mailbox changed?
  -> Yes: Schedule triage pass (with debounce)
  -> No: Ignore (e.g., ContactCard-only changes)
```

### Debounce Considerations

Multiple rapid state changes (e.g., batch email arrival, user applying labels quickly) should be collapsed into a single triage pass to avoid:
- Redundant API calls
- Race conditions between overlapping triage passes
- Wasted processing on intermediate states

**Proposed debounce strategy:**
1. On first state event, start a debounce timer (e.g., 3-5 seconds)
2. On subsequent events during the debounce window, reset the timer
3. When timer expires, trigger a single triage pass
4. The discovery script's output will reveal natural event clustering, informing the optimal debounce window

### Reconnection Strategy

SSE connections can drop due to network issues, server restarts, or load balancing. The strategy:

1. **Immediate reconnect** on clean disconnect (server-side close)
2. **Exponential backoff** on error disconnects (1s, 2s, 4s, 8s, max 60s)
3. **Honor `retry:` field** if the server provides a suggested reconnection interval
4. **State reconciliation** on reconnect: after reconnecting, do one full poll to catch any events missed during the disconnect gap

### Hybrid Approach (Recommended)

Use EventSource as the primary trigger with polling as a safety net:

- **Primary:** EventSource connection triggers triage on state changes (low latency, ~1-5s)
- **Fallback:** Poll every 5 minutes regardless of EventSource status (catches missed events)
- **Health check:** If EventSource disconnects and cannot reconnect within 60s, increase poll frequency to every 30s until SSE is restored

This provides the best of both worlds: low latency when SSE is working, and reliability through polling when it is not.

## Open Questions

1. **Event latency:** How quickly do events fire after an email arrives? (sub-second? 1-2 seconds?)
2. **Label vs. email events:** Do label changes (applying @ToImbox) trigger separate events from email state changes?
3. **Debounce window:** What is the practical minimum debounce window based on observed event clustering?
4. **Rate limiting:** Does Fastmail rate-limit EventSource connections? What happens with multiple concurrent connections?
5. **Connection longevity:** How long does Fastmail keep an idle EventSource connection open before disconnecting?
6. **Type filtering:** If we subscribe to only `Email,Mailbox` (not `*`), do we still get all triage-relevant events?

## References

- [RFC 8620 Section 7.3: Event Source](https://www.rfc-editor.org/rfc/rfc8620#section-7.3)
- [W3C Server-Sent Events Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [Fastmail JMAP Documentation](https://www.fastmail.com/dev/jmap)
- Related todo: `.planning/todos/pending/2026-02-25-replace-polling-with-jmap-eventsource-push-and-debouncer.md`
- Discovery script: `.research/jmap-eventsource/eventsource_discovery.py`
