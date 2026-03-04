---
phase: 14-contact-provenance-tracking-for-clean-reset
verified: 2026-03-04T15:30:00Z
status: passed
score: 12/12 must-haves verified
---

# Phase 14: Contact Provenance Tracking Verification Report

**Phase Goal:** Track which contacts Mailroom created vs. merely annotated (adopted), enabling the reset command to delete created contacts entirely while only stripping notes from pre-existing ones. Includes config section rename, setup provisioning, and triage pipeline @MailroomWarning cleanup.
**Verified:** 2026-03-04T15:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Config uses `mailroom:` section with `label_error`, `label_warning`, `warnings_enabled`, `provenance_group` keys | VERIFIED | `MailroomSectionSettings` at config.py:291; `mailroom:` key on MailroomSettings:352 |
| 2 | Old `labels:` config key causes app to fail to start with a helpful migration message | VERIFIED | `reject_old_labels_key` model_validator at config.py:355–364; raises ValueError with "renamed to 'mailroom:'" |
| 3 | Setup CLI creates provenance group as kind=mailroom resource | VERIFIED | provisioner.py:93–97 adds `ResourceAction(kind="mailroom", name=provenance_name, ...)`; apply_resources routes non-@ mailroom resources through `carddav.create_group` at provisioner.py:175–197 |
| 4 | Provenance group is validated at startup alongside triage groups | VERIFIED | `__main__.py:128–131` passes `infrastructure_groups=[settings.mailroom.provenance_group]` to `validate_groups` |
| 5 | Sieve guidance does NOT mention provenance group | VERIFIED | grep for "provenance" in `sieve_guidance.py` returns no matches |
| 6 | New contacts are added to provenance group; existing contacts are not | VERIFIED | `carddav.py:845–846` — `add_to_group(provenance_group, ...)` only inside the `if not results:` branch (new contact path); absent from existing-contact path |
| 7 | Created contacts have "Created by Mailroom" in note; adopted contacts have "Adopted by Mailroom" | VERIFIED | `create_contact` note at carddav.py:450–454 includes "Created by Mailroom"; `upsert_contact` existing-contact path at carddav.py:912–927 includes "Adopted by Mailroom" |
| 8 | `check_membership()` does not return provenance group name (invisible to triage) | VERIFIED | carddav.py:789 — `if group_name in self._infrastructure_groups: continue` skips provenance group |
| 9 | @MailroomWarning is removed from all sender emails on every successful triage, then conditionally reapplied | VERIFIED | screener.py:391–398 — cleanup step before upsert; step 3a at screener.py:429–430 conditionally reapplies on name mismatch |
| 10 | Unmodified provenance contacts are DELETEd from CardDAV | VERIFIED | `delete_contact` at carddav.py:690–708; called in apply_reset step 7 at resetter.py:366–371 |
| 11 | User-modified provenance contacts get @MailroomWarning on their emails, notes stripped, removed from all groups | VERIFIED | Step 4 at resetter.py:317–330 applies `batch_add_labels`; step 5 at resetter.py:331–337 removes from provenance group; step 6 at resetter.py:339–363 strips notes |
| 12 | Reset follows exact 7-step operation order | VERIFIED | apply_reset comments at resetter.py:254–262 define all 7 steps; test_7step_operation_order validates order via mock call sequencing |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact | Provides | Level 1: Exists | Level 2: Substantive | Level 3: Wired | Status |
|----------|----------|-----------------|----------------------|----------------|--------|
| `src/mailroom/core/config.py` | MailroomSectionSettings model with provenance_group field | Yes | Yes — 427 lines, `class MailroomSectionSettings` at line 291, `reject_old_labels_key` validator | Yes — used by screener, provisioner, main, resetter | VERIFIED |
| `config.yaml.example` | Updated config with mailroom: section | Yes | Yes — `mailroom:` section at line 45, all 4 keys present | Yes — canonical reference for users | VERIFIED |
| `tests/test_config.py` | Config rename + provenance_group tests | Yes | Yes — tests for `settings.mailroom.*` access, `labels:` rejection, `provenance_group` exclusion from `contact_groups` | Yes — exercises config.py | VERIFIED |
| `src/mailroom/clients/carddav.py` | infrastructure_groups exclusion, provenance_group param on upsert_contact, provenance note lines | Yes | Yes — `_infrastructure_groups: set[str]` at line 73; `check_membership` exclusion at line 789; "Created by Mailroom" at line 452; provenance_group param at line 815 | Yes — called from screener, resetter | VERIFIED |
| `src/mailroom/clients/jmap.py` | batch_add_labels() method | Yes | Yes — `def batch_add_labels` at line 373; mirrors batch_remove_labels with True patch | Yes — called from apply_reset step 4 | VERIFIED |
| `src/mailroom/reset/resetter.py` | Provenance-aware plan_reset and apply_reset with 7-step order | Yes | Yes — `_is_user_modified` at line 31; three-way `ContactCleanup.provenance` field; `contacts_to_delete/warn/strip` in ResetPlan; 7-step apply_reset | Yes — called from run_reset | VERIFIED |
| `src/mailroom/reset/reporting.py` | Updated reporting for provenance-aware reset | Yes | Yes — "Contacts to DELETE", "Contacts to WARN", "Contacts to strip (adopted)" sections; no "Likely Mailroom-Created" | Yes — called from run_reset | VERIFIED |
| `src/mailroom/workflows/screener.py` | @MailroomWarning cleanup in _process_sender | Yes | Yes — step 1b cleanup at line 391–398; `provenance_group=self._settings.mailroom.provenance_group` at line 404 | Yes — part of poll loop | VERIFIED |
| `src/mailroom/setup/provisioner.py` | Provenance group as kind=mailroom resource | Yes | Yes — provenance group appended as `ResourceAction(kind="mailroom", ...)` at line 95–97; apply_resources routes non-@ mailroom resources through carddav.create_group | Yes — called from run_setup | VERIFIED |
| `tests/test_resetter.py` | Tests for provenance DELETE, user-modified detection, 7-step order, adopted cleanup | Yes | Yes — 31 tests including test_provenance_unmodified_goes_to_delete, test_7step_operation_order, test_second_reset_warned_contacts_invisible, _is_user_modified suite | Yes — exercises resetter.py | VERIFIED |
| `tests/test_carddav_client.py` | Tests for provenance group add/skip, note format, check_membership exclusion | Yes | Yes — 11 new tests per summary; covers infrastructure_groups exclusion, "Created by Mailroom", "Adopted by Mailroom", provenance_group creation-only | Yes — exercises carddav.py | VERIFIED |
| `tests/test_screener_workflow.py` | Tests for @MailroomWarning cleanup and reapply, provenance plumbing | Yes | Yes — TestWarningCleanupBeforeProcessing, TestWarningCleanupThenReapply, TestWarningCleanupNoReapply, TestProvenanceGroupPlumbing | Yes — exercises screener.py | VERIFIED |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/mailroom/core/config.py` | `src/mailroom/workflows/screener.py` | `settings.mailroom.label_error`, `settings.mailroom.label_warning`, `settings.mailroom.provenance_group` | WIRED | screener.py:178, 279, 328, 394, 404 all use `self._settings.mailroom.*` |
| `src/mailroom/core/config.py` | `src/mailroom/setup/provisioner.py` | `settings.mailroom.label_error`, `settings.mailroom.provenance_group` | WIRED | provisioner.py:58, 93 |
| `src/mailroom/__main__.py` | `src/mailroom/clients/carddav.py` | `validate_groups` includes provenance group as infrastructure_group | WIRED | `__main__.py:128–131` passes both `required_groups` and `infrastructure_groups=[settings.mailroom.provenance_group]` |
| `src/mailroom/clients/carddav.py` | `check_membership` | `infrastructure_groups` set excludes provenance group | WIRED | carddav.py:789 — `if group_name in self._infrastructure_groups: continue` |
| `src/mailroom/clients/carddav.py` | `upsert_contact` | `provenance_group` parameter for add_to_group on creation | WIRED | carddav.py:815 param; called at carddav.py:845–846 |
| `src/mailroom/workflows/screener.py` | `src/mailroom/clients/jmap.py` | `batch_remove_labels` for @MailroomWarning cleanup | WIRED | screener.py:398 calls `self._jmap.batch_remove_labels(all_sender_emails, [warning_id])` |
| `src/mailroom/reset/resetter.py` | `src/mailroom/clients/carddav.py` | `delete_contact` for unmodified provenance contacts | WIRED | resetter.py:368 calls `carddav.delete_contact(contact.href, contact.etag)` |
| `src/mailroom/reset/resetter.py` | `src/mailroom/clients/jmap.py` | `batch_add_labels` for @MailroomWarning on warned contacts | WIRED | resetter.py:324 calls `jmap.batch_add_labels(sender_emails, [warning_mb_id])` |
| `src/mailroom/reset/resetter.py` | `src/mailroom/clients/carddav.py` | `get_group_members` for provenance group membership check | WIRED | resetter.py:195 calls `carddav.get_group_members(provenance_group)` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PROV-01 | 14-01 | Config `labels:` renamed to `mailroom:` with keys `label_error`, `label_warning`, `warnings_enabled`, `provenance_group` | SATISFIED | `MailroomSectionSettings` at config.py:291; all 4 fields present |
| PROV-02 | 14-01 | App fails to start if config uses old `labels:` key | SATISFIED | `reject_old_labels_key` validator at config.py:355–364 |
| PROV-03 | 14-01 | Setup CLI creates and validates provenance contact group as kind="mailroom" | SATISFIED | provisioner.py:93–97; apply_resources routes through carddav.create_group |
| PROV-04 | 14-02 | New contacts added to provenance group on creation; existing contacts never added | SATISFIED | carddav.py:845–846; provenance_group add only inside new-contact branch |
| PROV-05 | 14-02 | Contact notes include "Created by Mailroom" (new) or "Adopted by Mailroom" (existing) | SATISFIED | carddav.py:452, 912–927 |
| PROV-06 | 14-02 | Provenance group invisible to triage pipeline via `check_membership()` exclusion | SATISFIED | carddav.py:789 infrastructure_groups exclusion |
| PROV-07 | 14-02 | @MailroomWarning removed from all sender emails on every successful triage, reapplied if condition persists | SATISFIED | screener.py:391–430 |
| PROV-08 | 14-03 | CardDAV `delete_contact()` method for HTTP DELETE with ETag concurrency | SATISFIED | carddav.py:690–708 |
| PROV-09 | 14-03 | User-modified detection identifies contacts with vCard fields beyond what Mailroom creates | SATISFIED | resetter.py:31–59; `MAILROOM_MANAGED_FIELDS` set; `_SYSTEM_FIELD_PREFIXES` exclusion |
| PROV-10 | 14-03 | Reset DELETEs unmodified provenance contacts, WARNs user-modified, strips adopted | SATISFIED | apply_reset steps 4–7 at resetter.py:317–371; three-way ContactCleanup.provenance classification |
| PROV-11 | 14-03 | Reset follows exact 7-step operation order | SATISFIED | apply_reset at resetter.py:252–373; test_7step_operation_order validates ordering |

All 11 PROV requirements satisfied. No orphaned requirements found. REQUIREMENTS.md traceability table marks all PROV-01 through PROV-11 as Complete for Phase 14.

---

### Anti-Patterns Found

No blockers or stubs detected.

| File | Pattern Checked | Finding |
|------|-----------------|---------|
| `src/mailroom/reset/resetter.py` | TODO/FIXME, empty returns, console.log | None |
| `src/mailroom/clients/carddav.py` | TODO/FIXME, placeholder | None |
| `src/mailroom/clients/jmap.py` | TODO/FIXME, stub returns | None |
| `src/mailroom/workflows/screener.py` | TODO/FIXME, missing wiring | None |
| `src/mailroom/setup/provisioner.py` | TODO/FIXME, stub | None |
| `src/mailroom/reset/reporting.py` | "Likely Mailroom-Created" old pattern | Not present — correctly replaced |

One design note (not a gap): `resetter.py`'s `run_reset()` at line 433 calls `carddav.validate_groups(settings.contact_groups + [settings.mailroom.provenance_group])` without passing `infrastructure_groups=`. This is correct — `run_reset` never calls `check_membership`, so the infrastructure exclusion is not needed in the reset context. Reset uses `get_group_members` on the provenance group directly to classify contacts.

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
Expected: Those contacts are deleted from Fastmail Contacts entirely.
Why human: Requires real CardDAV DELETE to Fastmail.

**5. Provenance-aware reset: WARN path**

Test: Manually add a phone number to a Mailroom-created contact, then run `mailroom reset --apply`.
Expected: The contact is NOT deleted; @MailroomWarning is applied to their emails; note is stripped; contact is removed from provenance group but remains in Fastmail Contacts.
Why human: Requires real Fastmail state inspection.

**6. Config migration rejection**

Test: Use a `config.yaml` that still has a `labels:` section with non-default values.
Expected: `mailroom` fails to start with a clear message mentioning "renamed to 'mailroom:'".
Why human: Can be tested locally but confirms the user-facing error message quality.

---

### Test Suite Results

Full test suite: **416 passed, 0 failed** (run at verification time).
No `settings.labels.*` references remain in `src/` or `tests/`.
`class LabelSettings` does not exist in `src/`.
"Likely Mailroom-Created" pattern does not appear in `src/`.

---

### Gaps Summary

No gaps. All 12 truths verified. All 11 PROV requirements satisfied. All artifacts exist, are substantive, and are correctly wired. Full test suite green.

---

_Verified: 2026-03-04T15:30:00Z_
_Verifier: Claude (gsd-verifier)_
