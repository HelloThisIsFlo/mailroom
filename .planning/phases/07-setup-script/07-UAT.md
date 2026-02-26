---
status: complete
phase: 07-setup-script
source: 07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md
started: 2026-02-26T15:10:00Z
updated: 2026-02-26T15:25:00Z
---

## Current Test

[testing complete]

## Tests

### 1. CLI Help Shows Subcommands
expected: Running `mailroom --help` shows help text with both `setup` and `run` listed as commands.
result: pass

### 2. Backward Compatibility (no subcommand)
expected: Running `python -m mailroom` with no subcommand invokes the polling/screener service (same behavior as before phase 07).
result: pass

### 3. Setup Dry-Run Output
expected: Running `mailroom setup` (no --apply) shows a terraform-style resource plan grouped into Mailboxes, Action Labels, and Contact Groups with status symbols. No resources are actually created. Exit cleanly.
result: pass

### 4. Setup Apply Creates Resources
expected: Running `mailroom setup --apply` connects to Fastmail, creates any missing mailboxes/labels/contact groups, and reports what was created vs. what already existed. Shows summary line with counts.
result: pass

### 5. Setup Idempotency
expected: Running `mailroom setup --apply` a second time shows all resources as "exists" (nothing new created). No errors.
result: pass

### 6. Sieve Guidance (Default Mode)
expected: After the resource plan/apply output, setup prints sieve-style routing rule snippets for each root triage category (e.g., Imbox, Screener) showing the contact group condition and target folder.
result: pass

### 7. Sieve Guidance (UI Guide Mode)
expected: Running `mailroom setup --ui-guide` prints step-by-step Fastmail Settings instructions instead of sieve snippets, telling you how to create routing rules in the Fastmail web UI.
result: pass

### 8. Human Test 14: Setup Dry-Run
expected: Running `python human-tests/test_14_setup_dry_run.py` passes all checks — validates output format, sieve guidance presence, and confirms no resources were created.
result: pass

### 9. Human Test 15: Setup Apply + Idempotency
expected: Running `python human-tests/test_15_setup_apply.py` passes all checks — validates resource creation, sieve guidance output, and idempotent re-run behavior.
result: pass

## Summary

total: 9
passed: 9
issues: 0
pending: 0
skipped: 0

## Gaps

- truth: "Setup output is easy to scan with clear visual hierarchy"
  status: failed
  reason: "User reported: output too verbose, sieve rules cause scrolling, exists vs create not visually distinct, need 4 categories not 3"
  severity: minor
  test: 4
  root_cause: ""
  artifacts: []
  missing:
    - "Move sieve rules section before resource plan so resources are at the bottom"
    - "Add color to distinguish exists vs create status"
    - "Split into 4 categories: Mailboxes, Action Labels, Contact Groups, Mailroom-specific (errors/warnings)"
  debug_session: ""

- truth: "UI guide mode highlights overridden names (e.g., Inbox vs Imbox) with distinct color"
  status: failed
  reason: "User reported: override names like Inbox (from Imbox) should be highlighted in a different color to show they differ from the category name"
  severity: cosmetic
  test: 7
  root_cause: ""
  artifacts: []
  missing:
    - "Color-code folder names in UI guide output"
    - "Use different color for override names vs matching names"
  debug_session: ""
