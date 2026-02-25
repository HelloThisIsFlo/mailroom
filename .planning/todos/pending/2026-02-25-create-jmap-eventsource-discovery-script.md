---
created: 2026-02-25T16:53:50.330Z
title: Create JMAP EventSource discovery script
area: tooling
files:
  - human-tests/
---

## Problem

Before implementing push-based architecture, we need to understand the real-world behavior of JMAP EventSource on Fastmail. Questions to answer:
- How often do events fire?
- What do the event payloads look like?
- Which state changes trigger events (email arrival, label changes, contact updates)?
- Is there a practical debounce window we can derive from observed patterns?

## Solution

- Create a standalone discovery/debug script (similar to human-tests style)
- Connect to the JMAP EventSource endpoint using the existing Fastmail credentials
- Log all incoming events with timestamps, types, and payloads
- Let it run for a while during normal email activity to gather data
- Could live in `human-tests/` or a dedicated `scripts/` directory
