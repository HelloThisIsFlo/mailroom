---
created: 2026-02-28T16:43:29.100Z
title: Allow contact group reassignment via triage label
area: api
files:
  - src/mailroom/workflows/screener.py:310-319
---

## Problem

When a contact is already in a group (e.g. Paper Trail) and you apply a different triage label (e.g. `@ToJail`), Mailroom treats it as an error — applies `@MailroomError` and stops. This means you can't intentionally move a contact between groups by re-labeling.

Current behavior (`screener.py:311-319`):
- `_check_already_grouped` detects contact is in a different group
- Logs a warning (`already_grouped`)
- Applies `@MailroomError` label (not `@MailroomWarning`)
- Returns early without moving the contact

The log says "warning" but the label applied is the error label — there's a semantic mismatch too.

## Solution

Change the `already_grouped` handling to support intentional group reassignment:

1. **Move contact to new group** — remove from old group, add to new group via CardDAV
2. **Move emails** — re-file affected emails to the new destination mailbox
3. **Apply `@MailroomWarning`** (not error) — informational, the action was taken
4. **Log clearly** — `group_reassigned` event with old_group and new_group

Design consideration: should this be the default behavior, or require a confirmation mechanism (e.g. a special "force" label)? Starting with "just do it" is probably fine — the triage label is already an explicit user action.

Related but different:
- Todo "Scan for action labels beyond screener mailbox" — about *where* to look, not *what to do*
- Todo "Sweep workflow" — about re-labeling *emails* when groups drift, not reassigning groups
