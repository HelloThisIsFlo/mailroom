---
created: 2026-02-26T01:01:30.005Z
title: Sweep workflow: re-label archived emails by contact group membership
area: general
files: []
---

## Problem

Fastmail has a UX pitfall: when viewing a label mailbox (e.g. Paper Trail), the "archive" swipe/button doesn't archive the email — it **removes the label**. This means emails that were correctly triaged into Paper Trail (or any other category mailbox) can accidentally lose their label and disappear from that view.

The core issue is that the contact group membership (the source of truth for categorization) and the email's label can get out of sync. A contact in the "Paper Trail" group guarantees that all their emails *should* be in the Paper Trail mailbox, but the archive-swipe mistake silently breaks this invariant.

Currently there's no mechanism to detect or fix this. Once the label is removed, the email is effectively lost from the user's organized view even though the contact group still says it belongs there.

## Solution

Create a **pluggable "Sweep" workflow** — architecturally separate from the existing Screener workflow:

1. **Pluggable workflow architecture**: The Screener is one workflow (triage new emails in the Screener mailbox). The Sweep is a different workflow (audit all email against contact group membership). Both should be pluggable/composable — this is a far-future architecture goal.

2. **Sweep logic**: Periodically scan all emails (or recently modified emails). For each email:
   - Look up the sender's contact group membership
   - Determine which label(s) the email should have based on that group
   - If the email is missing the expected label (e.g. it was archived/removed by mistake), re-apply the label

3. **Contact group as source of truth**: The contact group is the durable, intentional categorization. Labels on individual emails can drift (via accidental swipes), but the group membership represents the user's actual intent.

4. **Scope & timing**: This is a far-future idea (different milestone entirely). May be discarded if the user changes their workflow. The key insight to preserve is: contact group membership can serve as a self-healing mechanism for label integrity.

5. **Performance considerations**: Scanning all email is expensive. May need incremental approaches (e.g., only check emails modified in the last N days, or use JMAP state tracking to detect changes).
