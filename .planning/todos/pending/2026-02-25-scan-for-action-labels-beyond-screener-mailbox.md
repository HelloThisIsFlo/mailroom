---
created: 2026-02-25T16:53:50.330Z
title: Scan for action labels beyond screener mailbox
area: api
files:
  - src/mailroom/screener_workflow.py
  - src/mailroom/fastmail_client.py
---

## Problem

Currently, the screener workflow only looks at emails in the Screener mailbox. But if a user changes their mind about a sender's classification after the email has already been triaged (e.g., moved to Paper Trail), that email will never be re-processed because it's no longer in the Screener.

More broadly: any email anywhere that has an action label (@-prefixed) could potentially be acted upon, regardless of which mailbox it's in.

## Solution

- Investigate whether we should scan all mailboxes (or specific ones) for emails with action labels
- Determine if the current triage logic already handles this case or not
- Consider performance implications of scanning beyond the Screener
- May need a separate "re-triage" or "sweep" workflow distinct from the main screener poll
- Design discussion needed — capture as future phase topic
