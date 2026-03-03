---
status: resolved
trigger: "CFG-02 validation for rejecting destination_mailbox: Inbox is case-sensitive"
created: 2026-03-03T00:00:00Z
updated: 2026-03-03T00:00:00Z
---

## Current Focus

hypothesis: confirmed - string comparison uses == "Inbox" (exact match, case-sensitive)
test: code reading
expecting: n/a
next_action: return diagnosis

## Symptoms

expected: destination_mailbox set to "inbox", "INBOX", "iNbOx" etc. should all be rejected by CFG-02 with the helpful error message
actual: only exact "Inbox" is caught; other casings bypass CFG-02 and fail later at mailbox resolution with "Required mailboxes not found in Fastmail"
errors: "Required mailboxes not found in Fastmail: inbox" (confusing, no guidance)
reproduction: set destination_mailbox to "inbox" (lowercase) in config.yaml
started: since CFG-02 was implemented in Phase 11-01

## Eliminated

(none needed - root cause found on first pass)

## Evidence

- timestamp: 2026-03-03T00:00:00Z
  checked: src/mailroom/core/config.py line 193
  found: `if resolved_mailbox == "Inbox"` -- exact string equality, case-sensitive
  implication: only the exact string "Inbox" is caught; "inbox", "INBOX" etc. pass through

- timestamp: 2026-03-03T00:00:00Z
  checked: src/mailroom/clients/jmap.py lines 136-150
  found: resolve_mailboxes looks up mailbox names by exact match in name_to_id dict; "inbox" won't match any Fastmail mailbox name, so it ends up in the `missing` list and raises ValueError
  implication: the fallback error is correct but unhelpful -- user gets "Required mailboxes not found" instead of the CFG-02 guidance

- timestamp: 2026-03-03T00:00:00Z
  checked: src/mailroom/__main__.py line 103
  found: MailroomSettings() is constructed without try/except; the ValueError from resolve_categories propagates through Pydantic's model_validator, wrapping it in a Pydantic ValidationError with full traceback
  implication: the helpful CFG-02 message IS there but buried inside a Pydantic ValidationError traceback

- timestamp: 2026-03-03T00:00:00Z
  checked: tests/test_config.py lines 610-631
  found: TestDestinationMailboxInboxRejected has 3 tests but all use exact "Inbox" -- no case-insensitive tests exist
  implication: test gap matches the code gap

## Resolution

root_cause: |
  config.py line 193 uses exact string equality `resolved_mailbox == "Inbox"`.
  This catches only the exact casing "Inbox" but not "inbox", "INBOX", or any other variant.

fix: (research only - not applied)
verification: (research only)
files_changed: []
