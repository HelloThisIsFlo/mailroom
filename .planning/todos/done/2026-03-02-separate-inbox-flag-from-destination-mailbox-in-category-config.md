---
created: 2026-03-02T16:13:21.382Z
title: Separate inbox flag from destination mailbox in category config
area: api
files:
  - src/mailroom/core/config.py:31
  - src/mailroom/core/config.py:52
  - src/mailroom/core/config.py:70
  - src/mailroom/workflows/screener.py
  - config.yaml:8-9
---

## Problem

Currently `Imbox` uses `destination_mailbox: Inbox` to file emails into Inbox. This conflates two independent concerns: *where* to file an email and *whether it should appear in Inbox*. There's no way to say "file under Feed AND show in Inbox" without making Feed's destination the Inbox itself (losing its own mailbox).

The two axes are:
1. **Destination mailbox** — which mailbox to move the email to (e.g., Feed, Paper Trail, Jail)
2. **Show in Inbox** — should this email also appear in Inbox?

These should be independent config options per category.

## Solution

Add an `add_to_inbox` boolean flag to `TriageCategory` / `ResolvedCategory`:

```yaml
triage:
  categories:
    - name: Imbox
      add_to_inbox: true          # appears in Inbox
      # destination_mailbox defaults to "Imbox" (no override needed)
    - name: Feed
      add_to_inbox: false         # default — Feed mailbox only
    - name: Person
      parent: Imbox
      contact_type: person
      add_to_inbox: true          # inherited from parent, or explicit
```

### Rules

- `destination_mailbox` must NEVER be `"Inbox"` — validation should reject this
- `add_to_inbox: true` means the email is added to Inbox *in addition to* its destination mailbox
- If `destination_mailbox` is null/empty AND `add_to_inbox: true` → inbox-only (no separate mailbox)
- `add_to_inbox` should inherit from parent like other fields

### Changes needed

1. **`config.py`**: Add `add_to_inbox: bool = False` to `TriageCategory`, add to `ResolvedCategory`, wire through resolution + parent inheritance
2. **`config.py`**: Add validation — reject `destination_mailbox: Inbox` with clear error
3. **`config.py`**: Allow `destination_mailbox` to be empty/null (for inbox-only categories)
4. **`screener.py`**: After filing to destination mailbox, also add Inbox keyword/label if `add_to_inbox` is true
5. **`config.yaml`**: Update Imbox category — remove `destination_mailbox: Inbox`, add `add_to_inbox: true`
6. **`defaults()`**: Update default Imbox to use new flag
7. **`required_mailboxes()`**: Inbox is always required; skip adding destination_mailbox if empty

### Migration

This is a breaking config change for anyone using `destination_mailbox: Inbox`. Should add a clear validation error message pointing to the new `add_to_inbox` flag.
