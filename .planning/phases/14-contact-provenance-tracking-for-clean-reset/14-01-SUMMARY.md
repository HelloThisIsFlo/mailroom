---
phase: 14-contact-provenance-tracking-for-clean-reset
plan: 01
subsystem: config
tags: [pydantic, config-migration, provenance, contact-groups]

# Dependency graph
requires:
  - phase: 11-config-layer
    provides: LabelSettings model and settings.labels access pattern
provides:
  - MailroomSectionSettings model with label_error, label_warning, warnings_enabled, provenance_group
  - Old labels: config key rejection with migration message
  - Provenance group provisioning as kind=mailroom resource
  - Startup validation includes provenance group
affects: [14-02, 14-03, reset, screener-workflow]

# Tech tracking
tech-stack:
  added: []
  patterns: [model_validator mode=before for config migration rejection]

key-files:
  created: []
  modified:
    - src/mailroom/core/config.py
    - src/mailroom/setup/provisioner.py
    - src/mailroom/workflows/screener.py
    - src/mailroom/__main__.py
    - src/mailroom/reset/resetter.py
    - config.yaml.example
    - tests/test_config.py
    - tests/test_provisioner.py
    - tests/test_screener_workflow.py

key-decisions:
  - "MailroomSectionSettings replaces LabelSettings with field renames: mailroom_error->label_error, mailroom_warning->label_warning"
  - "Provenance group uses kind=mailroom in provisioner (infrastructure, not triage)"
  - "apply_resources routes non-@ mailroom resources through carddav.create_group"

patterns-established:
  - "Config section migration: model_validator(mode=before) rejects old key with helpful message"
  - "Infrastructure groups (provenance) tracked as kind=mailroom, not kind=contact_group"

requirements-completed: [PROV-01, PROV-02, PROV-03]

# Metrics
duration: 6min
completed: 2026-03-04
---

# Phase 14 Plan 01: Config Rename + Provenance Group Summary

**Renamed config labels: to mailroom: section with provenance_group field, updated all 15+ references across codebase, provisioner creates provenance group at setup**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-04T14:24:01Z
- **Completed:** 2026-03-04T14:30:01Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Renamed LabelSettings to MailroomSectionSettings with label_error, label_warning, warnings_enabled, provenance_group fields
- Old `labels:` config key actively rejected with helpful migration message via model_validator(mode="before")
- All `settings.labels.*` references migrated to `settings.mailroom.*` across screener, provisioner, main, resetter
- Setup provisioner creates provenance group as kind="mailroom" contact group resource
- Startup validation (main and resetter) now includes provenance group alongside triage groups

## Task Commits

Each task was committed atomically:

1. **Task 1: Config model rename and provenance_group field** - `a653e13` (feat)
2. **Task 2: Update all settings.labels references + setup provisioner + startup validation** - `f42131c` (feat)

## Files Created/Modified
- `src/mailroom/core/config.py` - Renamed LabelSettings to MailroomSectionSettings, added provenance_group, added labels: rejection validator
- `config.yaml.example` - Renamed labels: to mailroom: section with new field names
- `src/mailroom/workflows/screener.py` - Updated 4 settings.labels references to settings.mailroom
- `src/mailroom/setup/provisioner.py` - Updated label references, added provenance group as mailroom resource, routing for contact group creation
- `src/mailroom/__main__.py` - Extended validate_groups to include provenance group
- `src/mailroom/reset/resetter.py` - Extended validate_groups to include provenance group
- `tests/test_config.py` - Updated assertions, added labels: rejection test and provenance_group exclusion test
- `tests/test_provisioner.py` - Updated mocks for provenance group, added provenance resource test
- `tests/test_screener_workflow.py` - Updated mock_settings.labels to mock_settings.mailroom

## Decisions Made
- MailroomSectionSettings replaces LabelSettings with field renames: mailroom_error -> label_error, mailroom_warning -> label_warning
- Provenance group tracked as kind="mailroom" in provisioner (infrastructure, not triage)
- apply_resources distinguishes mailroom mailboxes (@ prefix) from mailroom contact groups for correct creation routing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed provisioner test mocks missing provenance group**
- **Found during:** Task 2 (update provisioner references)
- **Issue:** Existing provisioner tests (test_all_exist, test_some_missing, test_categorizes_correctly) only mocked triage contact groups, not the provenance group, causing "create" status assertions to fail
- **Fix:** Added provenance group to mock carddav existing_groups in relevant tests
- **Files modified:** tests/test_provisioner.py
- **Verification:** All provisioner tests pass
- **Committed in:** f42131c (Task 2 commit)

**2. [Rule 2 - Missing Critical] Added mailroom contact group routing in apply_resources**
- **Found during:** Task 2 (provisioner provenance group)
- **Issue:** apply_resources treated all kind="mailroom" resources as JMAP mailboxes, but provenance group needs carddav.create_group()
- **Fix:** Split mailroom resources into mailboxes (@ prefix) and groups (non-@), route groups through carddav.create_group
- **Files modified:** src/mailroom/setup/provisioner.py
- **Verification:** Full test suite passes (379 tests)
- **Committed in:** f42131c (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Config foundation complete with mailroom: section and provenance_group field
- Provisioner creates provenance group at setup
- Ready for Phase 14 Plan 02 (provenance tracking in contact upsert)

## Self-Check: PASSED

All files exist. All commits verified (a653e13, f42131c). Full test suite: 379 passed.

---
*Phase: 14-contact-provenance-tracking-for-clean-reset*
*Completed: 2026-03-04*
