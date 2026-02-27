---
created: 2026-02-25T16:53:50.330Z
title: Replace polling with JMAP EventSource push and debouncer
area: api
files:
  - src/mailroom/screener_workflow.py
---

## Problem

The current ScreenerWorkflow uses a poll-based approach (`poll()`) to check for new emails. JMAP supports EventSource (Server-Sent Events) which would allow a push-based architecture — the server notifies us when state changes occur instead of us repeatedly asking.

A debouncer would be needed to batch rapid-fire events (e.g., multiple emails arriving in quick succession) into a single triage pass, avoiding redundant processing.

## Solution

- Research JMAP EventSource specification (RFC 8620 §7.3)
- Implement SSE connection to Fastmail's event endpoint
- Add debounce logic: accumulate events over a short window, then trigger a single triage pass
- Graceful fallback to polling if SSE connection drops
- Depends on: JMAP EventSource discovery script (for understanding event shape/frequency first)
