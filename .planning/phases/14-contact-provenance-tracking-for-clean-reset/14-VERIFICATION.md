---
phase: 14-contact-provenance-tracking-for-clean-reset
verified: 2026-03-04T18:00:00Z
status: passed
score: 17/17 must-haves verified
re_verification:
  previous_status: passed
  previous_score: 12/12
  note: >
    Previous verification predated Plans 14-04 and 14-05 (gap-closure plans
    executed after UAT). This re-verification covers all five plans and all
    17 must-have truths including the gap-closure additions.
  gaps_closed:
    - "Reset --apply moves emails to Screener before removing managed labels (RFC 8621 fix)"
    - "Step 6 skips contacts_to_delete to preserve original ETags for step 7"
    - "Config error message simplified to plain rejection (no migration guidance)"
    - "DRY RUN / APPLY mode banner displayed before any reset output"
    - "Progress indication printed during scan and apply phases"
    - "REV field unit test added to TestIsUserModified"
    - "MAILROOM_MANAGED_FIELDS documents REV dependency in code comments"
    - "Human integration test test_18 validates REV field behavior on Fastmail"
  gaps_remaining: []
  regressions: []
---

# Phase 14: Contact Provenance Tracking Verification Report

**Phase Goal:** Track which contacts Mailroom created vs. merely annotated (adopted), enabling the reset command to delete created contacts entirely while only stripping notes from pre-existing ones. Includes config section rename, setup provisioning, and triage pipeline @MailroomWarning cleanup.
**Verified:** 2026-03-04T18:00:00Z
**Status:** passed
**Re-verification:** Yes — covers all five plans (14-01 through 14-05), including two gap-closure plans added after UAT.

---

## Goal Achievement

### Observable Truths

All truths verified against actual source code. Line numbers are exact.

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Config uses `mailroom:` section with `label_error`, `label_warning`, `warnings_enabled`, `provenance_group` keys | VERIFIED | `MailroomSectionSettings` at config.py:291–298; `mailroom: MailroomSectionSettings` at config.py:352 |
| 2  | Old `labels:` config key rejected as unknown (no migration guidance) | VERIFIED | `reject_old_labels_key` at config.py:355–364 raises `"Unknown configuration key 'labels'. Valid top-level keys: triage, mailroom, logging, polling."` — no "renamed" in message; test_config.py:850–853 asserts `"renamed" not in msg.lower()` |
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
| 16 | Progress messages appear during scan and apply phases | VERIFIED | resetter.py:453 — `print_progress("Scanning mailboxes and contacts...")`; resetter.py:461 — `print_progress("Applying reset...")`; reporting.py:31–38 — `print_progress` defined |
| 17 | REV field unit test exists; MAILROOM_MANAGED_FIELDS documents REV dependency | VERIFIED | resetter.py:23–35 — multi-line comment block explaining REV is intentionally absent; tests/test_resetter.py:834 — `test_rev_field_alone_returns_true` in TestIsUserModified |

**Score:** 17/17 truths verified

---

### Required Artifacts

| Artifact | Provides | Exists | Substantive | Wired | Status |
|----------|----------|--------|-------------|-------|--------|
| `src/mailroom/core/config.py` | MailroomSectionSettings with provenance_group; reject_old_labels_key simplified | Yes | Yes — `class MailroomSectionSettings` at line 291, `reject_old_labels_key` at line 355–364, "Unknown configuration key" message | Yes — imported by screener, provisioner, main, resetter | VERIFIED |
| `config.yaml.example` | Updated config with mailroom: section | Yes | Yes — `mailroom:` section with all 4 keys | Yes — canonical reference for users | VERIFIED |
| `tests/test_config.py` | Config rename + provenance_group tests; reject_old_labels_key tests | Yes | Yes — `TestConfigLabelsRenamedToMailroom` at line 834–865; asserts "unknown" in msg, "renamed" not in msg | Yes — exercises config.py | VERIFIED |
| `src/mailroom/clients/carddav.py` | infrastructure_groups exclusion; provenance_group param on upsert_contact; "Created by Mailroom" / "Adopted by Mailroom" note lines; delete_contact | Yes | Yes — `_infrastructure_groups: set[str]` at line 73; `check_membership` exclusion at line 789; "Created by Mailroom" at line 452; `def delete_contact` at line 690 | Yes — called from screener, resetter | VERIFIED |
| `src/mailroom/clients/jmap.py` | batch_add_labels() method | Yes | Yes — `def batch_add_labels` at line 373; mirrors batch_remove_labels with `True` patch | Yes — called from apply_reset steps 1 and 4 | VERIFIED |
| `src/mailroom/reset/resetter.py` | Provenance-aware plan_reset and apply_reset with 7-step order; step 1 RFC 8621 fix; step 6 skips delete targets; progress and banner calls | Yes | Yes — `_is_user_modified` at line 40; three-way `ContactCleanup.provenance` at line 87; `contacts_to_delete/warn/strip` in ResetPlan; 7-step apply_reset; `batch_add_labels(email_ids, [screener_mb_id])` at line 303; `all_contacts = plan.contacts_to_warn + plan.contacts_to_strip` at line 354; REV comment block at line 23–35 | Yes — called from run_reset | VERIFIED |
| `src/mailroom/reset/reporting.py` | print_mode_banner, print_progress, provenance-aware print_reset_report | Yes | Yes — `print_mode_banner` at line 10 with DRY RUN/APPLY variants; `print_progress` at line 31; three report sections: "Contacts to DELETE", "Contacts to WARN", "Contacts to strip (adopted)" | Yes — imported and called from run_reset | VERIFIED |
| `src/mailroom/workflows/screener.py` | @MailroomWarning cleanup in _process_sender | Yes | Yes — step 1b cleanup wiring; `provenance_group=self._settings.mailroom.provenance_group` at upsert_contact call | Yes — part of poll loop | VERIFIED |
| `src/mailroom/setup/provisioner.py` | Provenance group as kind=mailroom resource | Yes | Yes — provenance group appended as `ResourceAction(kind="mailroom", ...)` at line 95–97 | Yes — called from run_setup | VERIFIED |
| `tests/test_resetter.py` | Full test coverage including RFC 8621 fix, step 6 skip, REV field | Yes | Yes — `test_step1_moves_emails_to_screener_before_removing_label`, `test_step1_resolves_screener_mailbox`, `test_step6_skips_contacts_to_delete`, `test_step7_deletes_unmodified_provenance_contacts`, `test_7step_operation_order`, `test_rev_field_alone_returns_true` | Yes — exercises resetter.py | VERIFIED |
| `tests/test_carddav_client.py` | Tests for provenance group add/skip, note format, check_membership exclusion, delete_contact | Yes | Yes — infrastructure_groups exclusion, "Created by Mailroom", "Adopted by Mailroom", provenance_group creation-only, delete_contact HTTP DELETE | Yes — exercises carddav.py | VERIFIED |
| `tests/test_screener_workflow.py` | Tests for @MailroomWarning cleanup and reapply, provenance plumbing | Yes | Yes — TestWarningCleanupBeforeProcessing, TestWarningCleanupThenReapply, TestWarningCleanupNoReapply, TestProvenanceGroupPlumbing | Yes — exercises screener.py | VERIFIED |
| `human-tests/test_18_rev_field_user_modification.py` | Human integration test validating Fastmail adds REV on contact edit | Yes | Yes — 232-line script; creates test contact, asks human to edit in Fastmail UI, re-fetches vCard, checks REV field presence and _is_user_modified(), cleans up; valid Python (syntax verified) | Yes — imports and calls CardDAVClient, _is_user_modified | VERIFIED |

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
| `src/mailroom/reset/resetter.py` | `src/mailroom/reset/reporting.py` | `print_mode_banner` and `print_progress` | WIRED | resetter.py:402 imports all three; line 450 calls `print_mode_banner(apply)`; lines 453, 461 call `print_progress(...)` |
| `src/mailroom/cli.py` | `src/mailroom/reset/resetter.py` | `run_reset(apply=bool)` | WIRED | cli.py `reset` command calls `run_reset(apply=apply)` |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| PROV-01 | 14-01, 14-05 | Config `labels:` renamed to `mailroom:` with all 4 keys; error simplified to plain rejection | SATISFIED | `MailroomSectionSettings` at config.py:291; `reject_old_labels_key` message: "Unknown configuration key 'labels'." with no "renamed" language (14-05 gap fixed) |
| PROV-02 | 14-01 | App fails to start if config uses old `labels:` key | SATISFIED | `reject_old_labels_key` validator at config.py:355–364 |
| PROV-03 | 14-01 | Setup CLI creates and validates provenance contact group as kind="mailroom" | SATISFIED | provisioner.py:93–97; apply_resources routes through carddav.create_group |
| PROV-04 | 14-02 | New contacts added to provenance group on creation; existing contacts never added | SATISFIED | carddav.py:844–846; provenance_group add only inside new-contact branch |
| PROV-05 | 14-02 | Contact notes include "Created by Mailroom" (new) or "Adopted by Mailroom" (existing) | SATISFIED | carddav.py:452, 908–928 |
| PROV-06 | 14-02 | Provenance group invisible to triage pipeline via `check_membership()` exclusion | SATISFIED | carddav.py:789 infrastructure_groups exclusion |
| PROV-07 | 14-02 | @MailroomWarning removed from all sender emails on every successful triage | SATISFIED | screener.py warning cleanup before upsert, conditional reapply after |
| PROV-08 | 14-03 | CardDAV `delete_contact()` method for HTTP DELETE with ETag concurrency | SATISFIED | carddav.py:690–708 |
| PROV-09 | 14-03, 14-05 | User-modified detection identifies contacts with vCard fields beyond what Mailroom creates; REV field documented and unit-tested | SATISFIED | resetter.py:40–68 `_is_user_modified`; REV comment block at line 23–35; `test_rev_field_alone_returns_true` at tests/test_resetter.py:834 |
| PROV-10 | 14-03, 14-04 | Reset DELETEs unmodified provenance contacts; WARNs user-modified; strips adopted; RFC 8621 compliance (move to Screener before label removal) | SATISFIED | apply_reset 7 steps at resetter.py:296–385; step 1 RFC 8621 fix at line 303–304; step 6 skip-delete-targets fix at line 354 |
| PROV-11 | 14-03, 14-04 | Reset follows exact 7-step operation order | SATISFIED | apply_reset at resetter.py:296–385; `test_7step_operation_order` validates ordering including step 1 Screener add |

All 11 PROV requirements satisfied. No orphaned requirements found. REQUIREMENTS.md marks all PROV-01 through PROV-11 as Complete for Phase 14.

---

### Anti-Patterns Found

No blockers or stubs detected.

| File | Pattern Checked | Finding |
|------|-----------------|---------|
| `src/mailroom/reset/resetter.py` | TODO/FIXME, empty returns, stub patterns | None |
| `src/mailroom/clients/carddav.py` | TODO/FIXME, placeholder, stub returns | None |
| `src/mailroom/clients/jmap.py` | TODO/FIXME, stub returns | None |
| `src/mailroom/workflows/screener.py` | TODO/FIXME, missing wiring | None |
| `src/mailroom/setup/provisioner.py` | TODO/FIXME, stub | None |
| `src/mailroom/reset/reporting.py` | "Likely Mailroom-Created" old pattern; no DRY RUN banner | Not present — correctly replaced; banner implemented |
| `src/mailroom/core/config.py` | "renamed to 'mailroom:'" migration guidance in error | Not present — error is plain rejection as required by PROV-01/14-05 |

One design note (not a gap): `resetter.py`'s `run_reset()` at line 447 calls `carddav.validate_groups(settings.contact_groups + [settings.mailroom.provenance_group])` without passing `infrastructure_groups=`. This is correct — `run_reset` never calls `check_membership`, so the infrastructure exclusion is not needed in the reset context. Reset uses `get_group_members` on the provenance group directly to classify contacts.

---

### Human Verification Required

The following behaviors require human testing against the real Fastmail account:

**1. Provenance group creation via setup CLI**

Test: Run `mailroom setup --apply` against a Fastmail account where the "Mailroom" contact group does not yet exist.
Expected: The group is created and appears in Fastmail Contacts.
Why human: Requires real CardDAV PUT to Fastmail; cannot verify via unit tests.

**2. Provenance tracking on real contact creation**

Test: Run `mailroom` service, send an email from a new address to Screener, apply a triage label.
Expected: Contact is created in Fastmail Contacts with "Created by Mailroom" note and added to "Mailroom" group.
Why human: Requires real JMAP + CardDAV round-trip.

**3. @MailroomWarning cleanup on successful triage**

Test: Triage an address that has @MailroomWarning on some emails.
Expected: @MailroomWarning is removed before the triage completes, then reapplied only if the name still mismatches.
Why human: Requires live label state in Fastmail.

**4. Provenance-aware reset: DELETE path**

Test: Run `mailroom reset --apply` against an account with unmodified Mailroom-created contacts.
Expected: Those contacts are deleted from Fastmail Contacts entirely; emails moved to Screener first (no RFC 8621 errors).
Why human: Requires real CardDAV DELETE and JMAP Email/set to Fastmail.

**5. Provenance-aware reset: WARN path**

Test: Manually add a phone number to a Mailroom-created contact, then run `mailroom reset --apply`.
Expected: The contact is NOT deleted; @MailroomWarning is applied to their emails; note is stripped; contact is removed from provenance group but remains in Fastmail Contacts.
Why human: Requires real Fastmail state inspection.

**6. Config migration rejection**

Test: Use a `config.yaml` that still has a `labels:` section.
Expected: `mailroom` fails to start with a message mentioning "Unknown configuration key 'labels'" and NOT mentioning "renamed".
Why human: Confirms the user-facing error message quality.

**7. DRY RUN / APPLY mode banner**

Test: Run `mailroom reset` (dry run) and `mailroom reset --apply`.
Expected: First line of output after connection is a prominent banner: cyan "DRY RUN — no changes will be made" (dry run) or red "APPLY MODE — changes will be permanent" (apply).
Why human: Visual appearance cannot be verified programmatically.

**8. REV field on contact edit (human-tests/test_18)**

Test: Run `python human-tests/test_18_rev_field_user_modification.py` against real Fastmail.
Expected: After editing the test contact in Fastmail UI, the re-fetched vCard contains a REV field that was absent before, and `_is_user_modified()` returns True.
Why human: Validates an implicit dependency of the provenance-aware reset on Fastmail's CardDAV server behavior.

---

### Test Suite Results

Full test suite: **418 passed, 0 failed** (run at re-verification time — 2 more tests than original 416 from Plans 14-04 and 14-05).
No `settings.labels.*` references remain in `src/` or `tests/`.
`class LabelSettings` does not exist in `src/`.
"Likely Mailroom-Created" pattern does not appear in `src/`.
Config error message contains "Unknown configuration key" and does NOT contain "renamed".

---

### Gaps Summary

No gaps. All 17 truths verified across all five plans (14-01 through 14-05). All 11 PROV requirements satisfied. All artifacts exist, are substantive, and are correctly wired. Full test suite green at 418 tests.

The original VERIFICATION.md (written after Plans 14-01 through 14-03) claimed `passed` with `12/12`. This re-verification confirms that the two gap-closure plans (14-04, 14-05) were fully and correctly implemented: the RFC 8621 bug fix, the ETag stale bug fix, the simplified config error message, the DRY RUN/APPLY mode banner, progress messages, the REV field unit test with code documentation, and the human integration test are all present in the codebase and tested.

---

_Verified: 2026-03-04T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
