---
phase: 07-setup-script
plan: 02
subsystem: cli, api
tags: [provisioner, terraform-style, dry-run, apply, jmap, carddav, reporting]

# Dependency graph
requires:
  - phase: 07-setup-script-01
    provides: Click CLI framework with setup stub, JMAPClient.create_mailbox, CardDAVClient.create_group
provides:
  - Provisioner with plan_resources() and apply_resources() orchestration
  - ResourceAction dataclass for resource status tracking
  - Terraform-style reporting with section headers and summary line
  - list_groups() helper on CardDAVClient for provisioning discovery
  - Working `mailroom setup` (dry-run) and `mailroom setup --apply`
affects: [07-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [Plan/apply provisioning pattern, Resource categorization into Mailboxes/Action Labels/Contact Groups, Parent-child dependency tracking with skip-on-failure]

key-files:
  created: [src/mailroom/setup/__init__.py, src/mailroom/setup/provisioner.py, src/mailroom/setup/reporting.py, tests/test_provisioner.py]
  modified: [src/mailroom/clients/carddav.py, src/mailroom/cli.py]

key-decisions:
  - "list_groups() added to CardDAVClient as clean helper for provisioning discovery (reuses same REPORT/vCard parsing as validate_groups)"
  - "Resources categorized per CONTEXT.md: Mailboxes = required_mailboxes minus triage_labels, Action Labels = triage_labels, Contact Groups = contact_groups"
  - "Pre-flight connectivity check catches HTTPStatusError and ConnectError separately for clear error messages"

patterns-established:
  - "Provisioner plan/apply: plan_resources builds ResourceAction list, apply_resources executes creates"
  - "Resource kind categorization: mailbox, label, contact_group with terraform-style grouped output"
  - "Parent-child skip: failed parent name tracked in set, children auto-skipped"

requirements-completed: [SETUP-01, SETUP-02, SETUP-03, SETUP-05, SETUP-06]

# Metrics
duration: 3min
completed: 2026-02-26
---

# Phase 07 Plan 02: Provisioner and Reporting Summary

**Terraform-style provisioner with plan/apply pattern, grouped resource reporting, and pre-flight connectivity checks for mailroom setup command**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T14:48:23Z
- **Completed:** 2026-02-26T14:51:31Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Provisioner with plan_resources() and apply_resources() orchestrating JMAP and CardDAV resource creation
- Terraform-style reporting grouped into Mailboxes, Action Labels, Contact Groups with status symbols and summary line
- Pre-flight connectivity check validates both JMAP and CardDAV before provisioning
- 229 total tests passing (219 existing + 10 new covering plan, apply, reporting, categorization)

## Task Commits

Each task was committed atomically:

1. **Task 1: Build provisioner with plan/apply pattern and reporting** - `ea5b4d1` (feat)
2. **Task 2: Wire CLI setup command to provisioner and add unit tests** - `ec1585c` (feat)

## Files Created/Modified
- `src/mailroom/setup/__init__.py` - Empty package init for setup module
- `src/mailroom/setup/provisioner.py` - run_setup(), plan_resources(), apply_resources() orchestration
- `src/mailroom/setup/reporting.py` - ResourceAction dataclass and print_plan() with terraform-style output
- `src/mailroom/clients/carddav.py` - Added list_groups() helper for provisioning discovery
- `src/mailroom/cli.py` - Replaced setup stub with real run_setup() call
- `tests/test_provisioner.py` - 10 unit tests: plan (3), apply (4), reporting (3)

## Decisions Made
- Added list_groups() to CardDAVClient as the cleanest approach for fetching all groups without requiring specific names (reuses same REPORT/vCard parsing pattern as validate_groups)
- Resources categorized per CONTEXT.md specification: required_mailboxes minus triage_labels = "Mailboxes", triage_labels = "Action Labels", contact_groups = "Contact Groups"
- Pre-flight catches HTTPStatusError and ConnectError separately for specific error messages (401 vs network failure)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Provisioner and reporting modules ready for Plan 03 sieve guidance integration
- run_setup() accepts ui_guide parameter (passed through, not yet used -- Plan 03 scope)
- list_groups() available for any future code needing group enumeration

---
*Phase: 07-setup-script*
*Completed: 2026-02-26*
