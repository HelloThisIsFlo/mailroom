---
created: 2026-03-02T00:59:17.323Z
title: Resolve v1.1 tech debt carry-forward in v1.2
area: general
files:
  - human-tests/test_13_docker_polling.py:95
  - src/mailroom/setup/sieve_guidance.py:43
  - tests/conftest.py:24-31
  - .planning/phases/09.1.1-helm-chart-migration-with-podsecurity-hardening/
---

## Problem

The v1.1 milestone audit (2026-03-02) passed with status `tech_debt` — all 18/18 requirements satisfied, but 4 non-blocking items accumulated. These should be resolved early in v1.2 before new feature work begins.

### Items

1. **Phase 09.1.1 missing VERIFICATION.md** — UAT 8/8 passed but no formal VERIFICATION.md was written. Process gap only (no requirement IDs assigned to this phase).

2. **`human-tests/test_13_docker_polling.py` line 95** — Sets `MAILROOM_POLL_INTERVAL=30` as env var, but post-config.yaml migration (Phase 9.1), polling interval is read from `config.yaml` only. The env var is silently ignored; test passes but at 60s instead of intended 30s.

3. **`src/mailroom/setup/sieve_guidance.py` line 43** — Accesses `settings._resolved_categories` (private attribute). Works correctly but fragile — would break silently if the attribute is renamed. Should expose a public `resolved_categories` property.

4. **`tests/conftest.py` lines 24-31** — Env var cleanup list scrubs 7 variable names that no longer map to any `MailroomSettings` field. Harmless but stale documentation that could confuse future contributors.

## Solution

Create a small tech debt phase at the start of v1.2 (or fold into first v1.2 phase):
- Item 1: Write VERIFICATION.md for Phase 09.1.1 based on UAT results
- Item 2: Update test_13 to pass poll interval via config.yaml volume mount instead of env var
- Item 3: Add `resolved_categories` public property on MailroomSettings, update sieve_guidance.py
- Item 4: Remove stale env var names from conftest.py cleanup list
