---
created: 2026-02-27T11:50:33.914Z
title: Investigate unexpected trigger=fallback polls after push events
area: api
files:
  - src/mailroom/__main__.py
  - src/mailroom/eventsource.py
---

## Problem

During UAT of phase 08 (EventSource push), the user observed `trigger=fallback` polls appearing ~60s after `trigger=push` polls, even though the SSE connection was active and working. Example from logs:

```
2026-02-27T11:36:53.410996Z [info     ] poll_completed                 component=main trigger=push
2026-02-27T11:37:54.009267Z [info     ] poll_completed                 component=main trigger=fallback
```

The ~60s gap matches `poll_interval=60`, suggesting the fallback timer fires even when SSE is connected and delivering push events. This may be expected behavior (safety-net polling regardless of SSE status) or it may indicate the queue.get timeout isn't being reset after a push-triggered poll.

Questions to investigate:
1. Is the fallback poll intentional as a safety net (poll even when SSE is working)?
2. Should `queue.get(timeout=poll_interval)` reset its timer after a push event so the next fallback is 60s from the last poll, not 60s from the start of the wait?
3. Does the drain-wait-drain debounce pattern affect the timing?

## Solution

TBD — needs investigation of the main loop's queue.get timing behavior in `__main__.py`. May be working as designed (safety-net polling) or may need the timeout to reset after each successful push-triggered poll.
