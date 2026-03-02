---
created: 2026-03-02T16:13:21.382Z
title: Change parent inheritance to additive label propagation
area: api
files:
  - src/mailroom/core/config.py:190-253
  - src/mailroom/workflows/screener.py
  - src/mailroom/setup/provisioner.py
  - src/mailroom/setup/sieve_guidance.py
  - config.yaml
---

## Problem

Current `parent` field means "inherit parent's `contact_group` and `destination_mailbox`." In practice this is useless — what's actually needed is for child categories to be fully independent categories that also apply their parent's label. The inheritance model conflates identity (what IS this category) with hierarchy (where does it ALSO appear).

Example of what's wrong today: `Person` with `parent: Imbox` inherits Imbox's contact group and destination mailbox, meaning Person emails go to Inbox — Person doesn't get its own mailbox or contact group unless explicitly overridden.

## Solution

Change `parent` semantics from "inherit properties" to "also apply parent's label(s)."

### New behavior

A child category is a **fully independent category** — it gets its own label, contact group, and destination mailbox derived from its name as normal. The only thing `parent` does is: when triaging, also apply the parent's label to the email.

**Billboard** (child of Paper Trail):
- Own resources: `@ToBillboard` label, `Billboard` contact group, `Billboard` mailbox
- On triage: email filed to `Billboard` mailbox, gets `Billboard` label AND `Paper Trail` label
- Email appears in both Billboard and Paper Trail

**Person** (child of Imbox):
- Own resources: `@ToPerson` label, `Person` contact group, `Person` mailbox
- On triage: email filed to `Person` mailbox, gets `Person` label AND `Imbox` label

### Nesting

Parents can be nested (e.g., `A → B → C`). An email triaged as `A` gets labels for `A`, `B`, and `C` — the full ancestor chain.

### What to remove

- Remove `contact_group` inheritance from parent in `resolve_categories()` (config.py:235-241)
- Remove `destination_mailbox` inheritance from parent in `resolve_categories()` (config.py:243-244)
- The two-pass resolution can simplify: pass 1 derives all fields from name, pass 2 just validates parent references exist

### What to add

- `ResolvedCategory` gets a new computed field: `parent_labels: list[str]` — the full ancestor chain of labels to also apply
- `resolve_categories()` builds this by walking the parent chain
- Validation: detect circular parent references
- `screener.py`: after filing to destination mailbox, also apply each label in `parent_labels`
- `provisioner.py` / `sieve_guidance.py`: setup script must create all resources for each child independently (no more shared contact groups)
- Sieve guidance should reflect that child rules apply parent labels too

### Open question

- Whether `add_to_inbox` (from the separate inbox flag todo) should inherit through parent — left undefined for now, decide during implementation.

### Config change

```yaml
# Before (inheritance-based)
- name: Person
  parent: Imbox
  contact_type: person
  # inherits Imbox's contact_group and destination_mailbox

# After (additive labels)
- name: Person
  parent: Imbox
  contact_type: person
  # gets own Person contact_group, Person mailbox
  # on triage: also applies Imbox label
```
