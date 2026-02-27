---
created: 2026-02-25T16:53:50.330Z
title: Create label and group setup script for Fastmail
area: tooling
files:
  - src/mailroom/config.py
  - src/mailroom/fastmail_client.py
---

## Problem

Currently, mailroom validates that required labels (action labels with @ prefix) and contact groups exist on Fastmail, and fails if they don't. The user must manually create these in the Fastmail UI. It would be much better to have a one-off setup script that reads the mapping config and replicates the required structure on Fastmail automatically.

Key unknowns to resolve:
- What if the structure already partially exists? (idempotency)
- What if existing labels/groups conflict with desired ones?
- Should this be a CLI command, a setup wizard, or a simple script?
- How to handle label hierarchy (parent/child mailboxes)?

## Solution

- Build as a standalone setup script (not run at service start — explicit user action)
- Read mapping config to determine required labels, groups, and mailbox structure
- Check what already exists on Fastmail via JMAP/CardDAV
- Create only what's missing (idempotent)
- Report what was created/skipped
- Lots of design discussion needed — capture as future phase topic
