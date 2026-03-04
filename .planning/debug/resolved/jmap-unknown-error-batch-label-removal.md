---
status: resolved
trigger: "JMAP 'unknown error' during batch label removal in mailroom reset"
created: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:00:00Z
---

## Current Focus

hypothesis: Removing a mailbox label from an email whose ONLY mailbox is that label results in empty mailboxIds, violating JMAP RFC 8621 constraint
test: Confirmed via RFC 8621 spec and code trace
expecting: Fastmail returns "unknown error" in notUpdated for those emails
next_action: Return diagnosis

## Symptoms

expected: `reset --apply` cleanly removes all managed labels (Feed, Jail, Paper Trail, etc.) from emails
actual: JMAP returns "unknown error" for many email IDs during batch label removal
errors: `StqPdiqlSeHN: unknown error, StqR9FK8sgRV: unknown error, ...`
reproduction: Run `reset --apply` when emails exist with only a single managed label
started: Since batch_remove_labels was added for reset

## Eliminated

(none -- primary hypothesis confirmed on first investigation)

## Evidence

- timestamp: 2026-03-04
  checked: RFC 8621 Section 4.1 - Email mailboxIds property
  found: "An Email in the mail store MUST belong to one or more Mailboxes at all times (until it is destroyed). The set is represented as an object, with each key being a Mailbox id."
  implication: Setting the LAST mailbox to null via patch syntax would produce an empty mailboxIds set, which violates the spec. Server rejects with error.

- timestamp: 2026-03-04
  checked: batch_remove_labels implementation (jmap.py:421-467)
  found: Patches `mailboxIds/{mb_id}: None` for each mailbox_id to remove. Does NOT check current mailbox membership first. Does NOT ensure email retains at least one mailbox.
  implication: If an email's only mailbox is the one being removed, the patch would leave mailboxIds empty -- spec violation.

- timestamp: 2026-03-04
  checked: apply_reset step 1 (resetter.py:287-293)
  found: Iterates managed labels independently. For each label, queries all emails in that mailbox, then calls batch_remove_labels to remove ONLY that label. Does not account for emails that might only exist in that single mailbox.
  implication: Emails filed ONLY to "Feed" (with no Inbox or other label) would fail when Feed label is removed because it's their only mailbox.

- timestamp: 2026-03-04
  checked: How emails get filed in normal workflow
  found: Workflow files emails to destination mailbox (e.g., Feed) and removes triage label. For categories without add_to_inbox=true, emails may end up with ONLY the destination mailbox as their label.
  implication: Feed, Jail, Paper Trail, Billboard, Truck emails (all without add_to_inbox) likely have only their destination mailbox. Removing that label = empty mailboxIds = JMAP error.

- timestamp: 2026-03-04
  checked: Fastmail error message format
  found: Fastmail returns "unknown error" as the description in notUpdated when patch would violate constraints. This matches the error format in the error handler: `f"{eid}: {err.get('description', 'unknown error')}"`.
  implication: Two possibilities -- (a) Fastmail literally sends `"description": "unknown error"` for this constraint violation, or (b) Fastmail sends an error WITHOUT a description field and the code's fallback `'unknown error'` kicks in. Either way, the root cause is the same.

## Resolution

root_cause: batch_remove_labels blindly removes labels without checking whether the email would be left with zero mailboxes. JMAP RFC 8621 requires emails to belong to at least one mailbox at all times. When the reset removes the only mailbox label from an email (e.g., removing "Feed" from an email that is ONLY in Feed), Fastmail rejects the update.

fix: (not applied -- diagnosis only)
verification: (not applied -- diagnosis only)
files_changed: []
