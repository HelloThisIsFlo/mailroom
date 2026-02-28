---
created: 2026-02-25T10:27:52.659Z
title: Make screener-label/contact-group/inbox-label mapping configurable
area: config
files:
  - src/mailroom/core/config.py:34-88
  - src/mailroom/workflows/screener.py
---

## Problem

The triage mapping between screener labels, contact groups, and inbox labels is currently hardcoded in `MailroomSettings` (e.g., `@ToPaperTrail` → `Paper Trail` group → `Paper Trail` destination). This limits Mailroom to a single triage workflow.

The user wants flexibility to define multiple triage categories beyond "Paper Trail" — for example:
- **Billboard**: ads worth seeing (others go to jail)
- **Truck**: delivery notifications
- **Bank**: invoices and financial correspondence

These could be subcategories of Paper Trail or entirely new top-level categories.

## Solution

Make the triage mapping configurable as a list of entries, each with three elements:
1. **Screener label** — the JMAP label that triggers triage (e.g., `@ToBillboard`)
2. **Contact group** — the CardDAV group to add the sender to (e.g., `Billboard`)
3. **Inbox label** — the "real" destination label applied to matching emails (e.g., `Billboard`, or could nest under `Paper Trail/Billboard`)

This replaces the current hardcoded `label_to_paper_trail` / `group_paper_trail` pattern in `config.py:34-88` with a dynamic list. The `triage_labels`, `triage_map`, `contact_groups`, and related properties would derive from this configurable list instead of individual settings.

Not urgent — verify current functionality works correctly first.
