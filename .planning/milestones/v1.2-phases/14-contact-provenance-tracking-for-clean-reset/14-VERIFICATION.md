---
phase: 14-contact-provenance-tracking-for-clean-reset
verified: 2026-03-04T20:13:52Z
status: passed
score: 20/20 must-haves verified
re_verification:
  previous_status: passed
  previous_score: 17/17
  note: >
    Previous verification (17/17) predated Plan 14-06 (confirmation prompt gap-closure,
    executed after UAT retest #3). This re-verification covers all six plans (14-01 through
    14-06) and adds 3 new truths from Plan 14-06's must_haves.
  gaps_closed:
    - "Reset --apply shows dry-run plan before executing"
    - "Reset --apply prompts user for confirmation before destructive operations"
    - "Declining confirmation aborts without making any changes"
    - "Non-interactive environments (piped stdin) abort safely"
  gaps_remaining: []
  regressions:
    - note: >
        Full test suite shows 96 failures in test_screener_workflow.py when run
        with other test files (cross-file structlog isolation issue). This is a
        PRE-EXISTING condition present in the codebase before Plan 14-06 (verified
        by stashing 14-06 changes and re-running: same 96 failures). All
        test_screener_workflow.py tests pass in isolation (143/143). All resetter,
        config, and carddav tests pass cleanly (170/170 in isolation). Not a
        Phase 14 regression.
---

# Phase 14: Contact Provenance Tracking Verification Report

**Phase Goal:** Track which contacts Mailroom created vs. merely annotated (adopted), enabling the reset command to delete created contacts entirely while only stripping notes from pre-existing ones. Includes config section rename, setup provisioning, and triage pipeline @MailroomWarning cleanup.
**Verified:** 2026-03-04T20:13:52Z
**Status:** passed
**Re-verification:** Yes — covers all six plans (14-01 through 14-06), including three gap-closure plans added after UAT.

---

## Goal Achievement

### Observable Truths

All truths verified against actual source code.

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Config uses `mailroom:` section with `label_error`, `label_warning`, `warnings_enabled`, `provenance_group` keys | VERIFIED | `MailroomSectionSettings` at config.py:291–298; `mailroom: MailroomSectionSettings` at config.py:352 |
| 2  | Old `labels:` config key rejected as unknown (no migration guidance) | VERIFIED | `reject_old_labels_key` at config.py:355–364 raises `"Unknown configuration key 'labels'."` — no "renamed" in message; test_config.py:850–853 asserts `"renamed" not in msg.lower()` |
| 3  | Setup CLI creates provenance group as kind=mailroom resource | VERIFIED | provisioner.py:93–97 appends `ResourceAction(kind="mailroom", name=provenance_name, ...)`; apply_resources routes non-@ mailroom resources through `carddav.create_group` |
| 4  | Provenance group is validated at startup alongside triage groups | VERIFIED | `__main__.py:128–131` calls `validate_groups(settings.contact_groups + [settings.mailroom.provenance_group], infrastructure_groups=[settings.mailroom.provenance_group])` |
| 5  | Sieve guidance does NOT mention provenance group | VERIFIED | No "provenance" in `sieve_guidance.py`; sieve output uses `resolved_categories` which excludes infrastructure groups |
| 6  | New contacts are added to provenance group; existing contacts are not | VERIFIED | carddav.py:844–846 — `add_to_group(provenance_group, ...)` inside `if not results:` branch only; absent from existing-contact path |
| 7  | Created contacts have "Created by Mailroom" in note; adopted contacts have "Adopted by Mailroom" | VERIFIED | create_contact note at carddav.py:450–454 includes "Created by Mailroom"; upsert_contact existing-contact path at carddav.py:908–928 includes "Adopted by Mailroom" |
| 8  | `check_membership()` does not return provenance group name (invisible to triage) | VERIFIED | carddav.py:789 — `if group_name in self._infrastructure_groups: continue` skips provenance group |
| 9  | @MailroomWarning is removed from all sender emails on every successful triage, then conditionally reapplied | VERIFIED | screener.py:391–398 — cleanup step before upsert; step 3a at screener.py:429–430 conditionally reapplies on name mismatch |
| 10 | Unmodified provenance contacts are DELETEd from CardDAV | VERIFIED | `delete_contact` at carddav.py:690–708; called in apply_reset step 7 at resetter.py:380–385 |
| 11 | User-modified provenance contacts get @MailroomWarning on their emails, notes stripped, removed from all groups | VERIFIED | Step 4 at resetter.py:331–343 applies `batch_add_labels`; step 5 at resetter.py:345–351 removes from provenance group; step 6 at resetter.py:353–374 strips notes |
| 12 | Reset follows exact 7-step operation order | VERIFIED | apply_reset comments at resetter.py:296–385 define all 7 steps; `test_7step_operation_order` validates order via mock call sequencing |
| 13 | Reset step 1 moves emails to Screener before removing managed labels (RFC 8621 compliance) | VERIFIED | resetter.py:297–307 — `batch_add_labels(email_ids, [screener_mb_id])` called BEFORE `batch_remove_labels(email_ids, [mb_id])` for every label; Screener resolved at resetter.py:285–299 |
| 14 | Reset step 6 skips contacts_to_delete (preserves original ETags for step 7 DELETE) | VERIFIED | resetter.py:354 — `all_contacts = plan.contacts_to_warn + plan.contacts_to_strip` — contacts_to_delete excluded; `test_step6_skips_contacts_to_delete` asserts `update_contact_vcard.call_count == 2` |
| 15 | Reset CLI prints prominent DRY RUN or APPLY banner before any output | VERIFIED | reporting.py:10–28 — `print_mode_banner(apply)` function; run_reset at resetter.py:450 calls it after group validation, before `plan_reset()` |
| 16 | Progress messages appear during scan and apply phases | VERIFIED | resetter.py:453 — `print_progress("Scanning mailboxes and contacts...")`; resetter.py:468 — `print_progress("Applying reset...")`; reporting.py:31–38 — `print_progress` defined |
| 17 | REV field unit test exists; MAILROOM_MANAGED_FIELDS documents REV dependency | VERIFIED | resetter.py:23–35 — multi-line comment block explaining REV is intentionally absent; tests/test_resetter.py:834 — `test_rev_field_alone_returns_true` in TestIsUserModified |
| 18 | Reset --apply shows the full dry-run plan before executing | VERIFIED | resetter.py:456–460 — `print_reset_report(reset_plan, apply=False)` called BEFORE confirmation gate and `apply_reset`; `test_apply_shows_plan_before_executing` validates order via call_order list |
| 19 | Reset --apply prompts user for confirmation before destructive operations | VERIFIED | reporting.py:62–81 — `print_confirmation_prompt()` with TTY check, YELLOW prompt, `input()` call; resetter.py:463 — `if not print_confirmation_prompt(): return 0` |
| 20 | Declining confirmation (or non-interactive stdin) aborts without making any changes | VERIFIED | resetter.py:463–465 — decline returns 0 before `apply_reset` call; `test_apply_declined_aborts_no_changes` asserts `apply_reset` not called and "Aborted" in output; `test_returns_false_on_non_tty` and `test_returns_false_on_eof_error` verify safe abort paths |

**Score:** 20/20 truths verified

---

### Required Artifacts

| Artifact | Provides | Exists | Substantive | Wired | Status |
|----------|----------|--------|-------------|-------|--------|
| `src/mailroom/core/config.py` | MailroomSectionSettings with provenance_group; reject_old_labels_key simplified | Yes | Yes — `class MailroomSectionSettings` at line 291, `reject_old_labels_key` at line 355–364 | Yes — imported by screener, provisioner, main, resetter | VERIFIED |
| `config.yaml.example` | Updated config with mailroom: section | Yes | Yes — `mailroom:` section with all 4 keys | Yes — canonical reference for users | VERIFIED |
| `tests/test_config.py` | Config rename + provenance_group tests; reject_old_labels_key tests | Yes | Yes — `TestConfigLabelsRenamedToMailroom`; asserts "unknown" in msg, "renamed" not in msg | Yes — exercises config.py | VERIFIED |
| `src/mailroom/clients/carddav.py` | infrastructure_groups exclusion; provenance_group param on upsert_contact; "Created by Mailroom" / "Adopted by Mailroom" note lines; delete_contact | Yes | Yes — `_infrastructure_groups: set[str]` at line 73; `check_membership` exclusion at line 789; "Created by Mailroom" at line 452; `def delete_contact` at line 690 | Yes — called from screener, resetter | VERIFIED |
| `src/mailroom/clients/jmap.py` | batch_add_labels() method | Yes | Yes — `def batch_add_labels` at line 373; mirrors batch_remove_labels with `True` patch | Yes — called from apply_reset steps 1 and 4 | VERIFIED |
| `src/mailroom/reset/resetter.py` | Provenance-aware plan_reset and apply_reset with 7-step order; confirmation gate wired into run_reset apply path | Yes | Yes — `_is_user_modified` at line 40; three-way `ContactCleanup.provenance` at line 87; `contacts_to_delete/warn/strip` in ResetPlan; 7-step apply_reset; `print_confirmation_prompt` imported at line 402; confirmation gate at lines 463–465; plan shown before prompt at line 457 | Yes — called from run_reset, cli.py | VERIFIED |
| `src/mailroom/reset/reporting.py` | print_mode_banner, print_progress, print_confirmation_prompt, provenance-aware print_reset_report | Yes | Yes — `print_mode_banner` at line 10; `print_progress` at line 31; `print_confirmation_prompt` at line 62–81 with TTY check, EOFError handler, YELLOW prompt, input(); three report sections | Yes — imported and called from run_reset | VERIFIED |
| `src/mailroom/workflows/screener.py` | @MailroomWarning cleanup in _process_sender | Yes | Yes — step 1b cleanup wiring; `provenance_group=self._settings.mailroom.provenance_group` at upsert_contact call | Yes — part of poll loop | VERIFIED |
| `src/mailroom/setup/provisioner.py` | Provenance group as kind=mailroom resource | Yes | Yes — provenance group appended as `ResourceAction(kind="mailroom", ...)` at line 95–97 | Yes — called from run_setup | VERIFIED |
| `tests/test_resetter.py` | Full test coverage including RFC 8621 fix, step 6 skip, REV field, confirmation prompt (6 tests), run_reset confirmation flow (3 tests) | Yes | Yes — `TestPrintConfirmationPrompt` (6 tests: y/Y/n/empty/non-tty/EOF), `TestRunResetConfirmation` (3 tests: plan-before-execute, confirmed-proceeds, declined-aborts); 42 total tests, all green | Yes — exercises resetter.py and reporting.py | VERIFIED |
| `tests/test_carddav_client.py` | Tests for provenance group add/skip, note format, check_membership exclusion, delete_contact | Yes | Yes — infrastructure_groups exclusion, "Created by Mailroom", "Adopted by Mailroom", provenance_group creation-only, delete_contact HTTP DELETE | Yes — exercises carddav.py | VERIFIED |
| `tests/test_screener_workflow.py` | Tests for @MailroomWarning cleanup and reapply, provenance plumbing | Yes | Yes — TestWarningCleanupBeforeProcessing, TestWarningCleanupThenReapply, TestWarningCleanupNoReapply, TestProvenanceGroupPlumbing; all 143 pass in isolation | Yes — exercises screener.py | VERIFIED |
| `human-tests/test_18_rev_field_user_modification.py` | Human integration test validating Fastmail adds REV on contact edit | Yes | Yes — 232-line script; creates test contact, asks human to edit in Fastmail UI, re-fetches vCard, checks REV field presence and _is_user_modified(), cleans up | Yes — imports and calls CardDAVClient, _is_user_modified | VERIFIED |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/mailroom/core/config.py` | `src/mailroom/workflows/screener.py` | `settings.mailroom.label_error`, `settings.mailroom.label_warning`, `settings.mailroom.provenance_group` | WIRED | screener.py uses `self._settings.mailroom.*` throughout |
| `src/mailroom/core/config.py` | `src/mailroom/setup/provisioner.py` | `settings.mailroom.label_error`, `settings.mailroom.provenance_group` | WIRED | provisioner.py:58, 93 |
| `src/mailroom/__main__.py` | `src/mailroom/clients/carddav.py` | `validate_groups` includes provenance group as infrastructure_group | WIRED | `__main__.py:128–131` passes both `required_groups` and `infrastructure_groups=[settings.mailroom.provenance_group]` |
| `src/mailroom/clients/carddav.py` | `check_membership` | `infrastructure_groups` set excludes provenance group | WIRED | carddav.py:789 — `if group_name in self._infrastructure_groups: continue` |
| `src/mailroom/clients/carddav.py` | `upsert_contact` | `provenance_group` parameter for add_to_group on creation only | WIRED | carddav.py:815 param; called at carddav.py:844–846 inside new-contact branch |
| `src/mailroom/workflows/screener.py` | `src/mailroom/clients/jmap.py` | `batch_remove_labels` for @MailroomWarning cleanup | WIRED | screener.py calls `self._jmap.batch_remove_labels(all_sender_emails, [warning_id])` |
| `src/mailroom/reset/resetter.py` | `src/mailroom/clients/carddav.py` | `delete_contact` for unmodified provenance contacts | WIRED | resetter.py:382 calls `carddav.delete_contact(contact.href, contact.etag)` |
| `src/mailroom/reset/resetter.py` | `src/mailroom/clients/jmap.py` | `batch_add_labels` for Screener move (step 1) and @MailroomWarning (step 4) | WIRED | resetter.py:303 calls `jmap.batch_add_labels(email_ids, [screener_mb_id])`; resetter.py:338 calls `jmap.batch_add_labels(sender_emails, [warning_mb_id])` |
| `src/mailroom/reset/resetter.py` | `src/mailroom/clients/carddav.py` | `get_group_members` for provenance group membership check | WIRED | resetter.py:204 calls `carddav.get_group_members(provenance_group)` |
| `src/mailroom/reset/resetter.py` | `src/mailroom/reset/reporting.py` | `print_mode_banner`, `print_progress`, `print_reset_report`, `print_confirmation_prompt` | WIRED | resetter.py:402 imports all four; line 450 calls `print_mode_banner(apply)`; line 453 calls `print_progress`; line 457 calls `print_reset_report(reset_plan, apply=False)`; line 463 calls `print_confirmation_prompt()` |
| `src/mailroom/cli.py` | `src/mailroom/reset/resetter.py` | `run_reset(apply=bool)` | WIRED | cli.py `reset` command calls `run_reset(apply=apply)` |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| PROV-01 | 14-01, 14-05 | Config `labels:` renamed to `mailroom:` with all 4 keys; error simplified to plain rejection | SATISFIED | `MailroomSectionSettings` at config.py:291; `reject_old_labels_key` message: "Unknown configuration key 'labels'." with no "renamed" language |
| PROV-02 | 14-01 | App fails to start if config uses old `labels:` key | SATISFIED | `reject_old_labels_key` validator at config.py:355–364 |
| PROV-03 | 14-01 | Setup CLI creates and validates provenance contact group as kind="mailroom" | SATISFIED | provisioner.py:93–97; apply_resources routes through carddav.create_group |
| PROV-04 | 14-02 | New contacts added to provenance group on creation; existing contacts never added | SATISFIED | carddav.py:844–846; provenance_group add only inside new-contact branch |
| PROV-05 | 14-02 | Contact notes include "Created by Mailroom" (new) or "Adopted by Mailroom" (existing) | SATISFIED | carddav.py:452, 908–928 |
| PROV-06 | 14-02 | Provenance group invisible to triage pipeline via `check_membership()` exclusion | SATISFIED | carddav.py:789 infrastructure_groups exclusion |
| PROV-07 | 14-02 | @MailroomWarning removed from all sender emails on every successful triage | SATISFIED | screener.py warning cleanup before upsert, conditional reapply after |
| PROV-08 | 14-03 | CardDAV `delete_contact()` method for HTTP DELETE with ETag concurrency | SATISFIED | carddav.py:690–708 |
| PROV-09 | 14-03, 14-05 | User-modified detection identifies contacts with vCard fields beyond what Mailroom creates; REV field documented and unit-tested | SATISFIED | resetter.py:40–68 `_is_user_modified`; REV comment block at line 23–35; `test_rev_field_alone_returns_true` at tests/test_resetter.py:834 |
| PROV-10 | 14-03, 14-04, 14-06 | Reset DELETEs unmodified provenance contacts; WARNs user-modified; strips adopted; RFC 8621 compliance; shows plan before execution; prompts for confirmation before apply | SATISFIED | apply_reset 7 steps at resetter.py:296–385; step 1 RFC 8621 fix at line 303–304; step 6 skip-delete-targets fix at line 354; plan shown at line 457; confirmation gate at lines 462–465 |
| PROV-11 | 14-03, 14-04 | Reset follows exact 7-step operation order | SATISFIED | apply_reset at resetter.py:296–385; `test_7step_operation_order` validates ordering |

All 11 PROV requirements satisfied. No orphaned requirements found. REQUIREMENTS.md marks all PROV-01 through PROV-11 as Complete for Phase 14.

---

### Anti-Patterns Found

No blockers or stubs detected.

| File | Pattern Checked | Finding |
|------|-----------------|---------|
| `src/mailroom/reset/resetter.py` | TODO/FIXME, empty returns, stub patterns | None |
| `src/mailroom/reset/reporting.py` | TODO/FIXME, placeholder, stub returns | None — `print_confirmation_prompt` is substantive (TTY check, EOFError, YELLOW prompt, input()) |
| `src/mailroom/clients/carddav.py` | TODO/FIXME, placeholder | None |
| `src/mailroom/clients/jmap.py` | TODO/FIXME, stub returns | None |
| `src/mailroom/workflows/screener.py` | TODO/FIXME, missing wiring | None |
| `src/mailroom/setup/provisioner.py` | TODO/FIXME, stub | None |
| `src/mailroom/core/config.py` | "renamed to 'mailroom:'" migration guidance in error | Not present — error is plain rejection as required |

Pre-existing condition (not introduced by Phase 14): Full test suite `python -m pytest tests/` shows 96 failures in `test_screener_workflow.py` when run alongside other test files. This is a cross-file structlog isolation issue present before and after Plan 14-06 (confirmed by stashing plan 14-06 changes: identical failure count). All screener tests pass in isolation (143/143). All resetter, carddav, and config tests pass cleanly regardless of run order (284/284 excluding screener tests).

---

### Human Verification Required

**1. Confirmation prompt interaction**

Test: Run `python -m mailroom reset --apply`. After the scan phase, see the dry-run plan, then "Proceed with reset? [y/N] " in yellow. Type "n" and verify "Aborted." is printed with no changes. Run again, type "y" and verify reset executes.
Expected: Full plan shown before destructive operations; "y" proceeds, anything else aborts.
Why human: TTY detection and interactive input require a real terminal session.

**2. Non-interactive abort**

Test: Run `echo "" | python -m mailroom reset --apply`.
Expected: "Non-interactive mode, aborting." printed; no changes made.
Why human: Tests real piped stdin behavior against actual process.

**3. Provenance group creation via setup CLI**

Test: Run `mailroom setup --apply` against a Fastmail account where the "Mailroom" contact group does not yet exist.
Expected: The group is created and appears in Fastmail Contacts.
Why human: Requires real CardDAV PUT to Fastmail.

**4. Full end-to-end reset with confirmation**

Test: Run `mailroom reset --apply` against an account with triage history. View the full dry-run plan, confirm with "y".
Expected: Emails moved to Screener; unmodified contacts deleted; modified contacts warned; adopted contacts stripped.
Why human: Requires real JMAP and CardDAV state in Fastmail.

**5. REV field on contact edit (human-tests/test_18)**

Test: Run `python human-tests/test_18_rev_field_user_modification.py` against real Fastmail.
Expected: After editing the test contact in Fastmail UI, the re-fetched vCard contains a REV field, and `_is_user_modified()` returns True.
Why human: Validates the implicit REV dependency against Fastmail's CardDAV server behavior.

---

### Test Suite Results

| Test file | Isolated | Full suite |
|-----------|----------|------------|
| `tests/test_resetter.py` | 42/42 pass | 42/42 pass |
| `tests/test_carddav_client.py` | pass | pass |
| `tests/test_config.py` | pass | pass |
| `tests/test_screener_workflow.py` | 143/143 pass | cross-contamination (pre-existing, not Phase 14) |
| All others | pass | pass |

New tests added in Plan 14-06: `TestPrintConfirmationPrompt` (6 tests) + `TestRunResetConfirmation` (3 tests) = 9 new tests. All green.

---

### Gaps Summary

No gaps. All 20 truths verified across all six plans (14-01 through 14-06). All 11 PROV requirements satisfied. All artifacts exist, are substantive, and are correctly wired. Key links verified at the import and call level. No stubs or placeholder patterns found.

The previous VERIFICATION.md (17/17, plans 14-01 through 14-05) missed one UAT gap: `reset --apply` executed immediately after the banner without showing the plan or prompting for confirmation. Plan 14-06 closed this gap by adding `print_confirmation_prompt()` to `reporting.py` (reporting.py:62–81) and wiring a confirmation gate into `run_reset()` at `resetter.py:462–465`. The plan is now always shown before the confirmation prompt (`resetter.py:457`), and the apply path only proceeds if the user confirms with "y" or "Y". This is fully implemented, tested (9 new unit tests, all green), and verified against the codebase.

---

_Verified: 2026-03-04T20:13:52Z_
_Verifier: Claude (gsd-verifier)_
