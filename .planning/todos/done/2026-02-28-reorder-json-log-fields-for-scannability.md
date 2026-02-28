---
created: 2026-02-28T16:52:00.000Z
title: Reorder JSON log fields for scannability
area: api
files:
  - src/mailroom/core/logging.py
---

## Problem

JSON log output has bound context fields first (`component`, `sender`, etc.) followed by processor-added fields (`level`, `timestamp`). This means `timestamp` and `level` appear at different positions depending on how many bound fields a log line has — makes it hard to visually scan `kubectl logs` or k9s output.

Current output:
```json
{"component": "screener", "sender": "amber@doppler.com", "event": "already_grouped", "level": "warning", "timestamp": "2026-02-28T..."}
```

## Solution

Add a reorder processor before `JSONRenderer` in `logging.py` (line ~34) that puts key fields first in a consistent order: `timestamp → level → component → event → ...remaining`.

```python
def reorder_keys(logger, method_name, event_dict):
    priority = ("timestamp", "level", "component", "event")
    ordered = {k: event_dict.pop(k) for k in priority if k in event_dict}
    ordered.update(event_dict)
    return ordered
```

Target output:
```json
{"timestamp": "2026-02-28T...", "level": "warning", "component": "screener", "event": "already_grouped", "sender": "amber@doppler.com"}
```

Small change, big readability win — works everywhere (kubectl logs, k9s, stern, Loki).
