---
status: resolved
trigger: "412 Precondition Failed bug in reset command: step 6 strips notes (changing ETag), step 7 deletes with stale ETag"
created: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - step 6 updates contacts_to_delete vCards (changing server ETag), step 7 uses original plan-time ETag for DELETE
test: Code trace of apply_reset steps 6 and 7
expecting: step 6 calls update_contact_vcard with contact.etag, server returns new ETag; step 7 calls delete_contact with same contact.etag (now stale)
next_action: Return diagnosis

## Symptoms

expected: Reset command deletes unmodified provenance contacts without error
actual: Step 7 DELETE fails with 412 Precondition Failed because the ETag is stale
errors: 412 Precondition Failed from CardDAV server on DELETE
reproduction: Run `mailroom reset --apply` with any contacts in contacts_to_delete list
started: Introduced in phase 14-03 (provenance-aware reset with 7-step order)

## Eliminated

(none - root cause identified on first hypothesis)

## Evidence

- timestamp: 2026-03-04T00:00:00Z
  checked: apply_reset step 6 (lines 340-360 in resetter.py)
  found: |
    Line 340: all_contacts = plan.contacts_to_delete + plan.contacts_to_warn + plan.contacts_to_strip
    Line 358: carddav.update_contact_vcard(contact.href, contact.etag, vcard_bytes)
    Step 6 iterates ALL annotated contacts (including contacts_to_delete) and calls
    update_contact_vcard with the plan-time contact.etag. The server accepts this PUT
    (ETag matches) and returns a NEW ETag. But the new ETag is NOT captured or stored
    back on the ContactCleanup object.
  implication: After step 6, the server-side ETag for contacts_to_delete entries has changed

- timestamp: 2026-03-04T00:00:00Z
  checked: apply_reset step 7 (lines 365-371 in resetter.py)
  found: |
    Line 368: carddav.delete_contact(contact.href, contact.etag)
    Step 7 calls delete_contact with the ORIGINAL contact.etag from plan time.
    But the server-side ETag was changed by step 6's PUT. So the If-Match header
    sends a stale ETag -> 412 Precondition Failed.
  implication: Step 7 always fails for any contact that step 6 successfully updated

- timestamp: 2026-03-04T00:00:00Z
  checked: carddav.delete_contact (lines 690-708 in carddav.py)
  found: |
    delete_contact sends DELETE with If-Match: etag header.
    No retry logic on 412 (unlike add_to_group/remove_from_group which retry).
    resp.raise_for_status() raises httpx.HTTPStatusError on 412.
  implication: No built-in recovery from stale ETag in delete path

- timestamp: 2026-03-04T00:00:00Z
  checked: carddav.update_contact_vcard (lines 710-734 in carddav.py)
  found: |
    update_contact_vcard RETURNS the new ETag (line 734: return resp.headers.get("etag", ""))
    But apply_reset step 6 (line 358) does NOT capture this return value.
  implication: The fix data is available - the new ETag is returned but discarded

- timestamp: 2026-03-04T00:00:00Z
  checked: test_step7_deletes_unmodified_provenance_contacts (test line 471)
  found: |
    carddav.delete_contact.assert_called_once_with("/uid-del.vcf", '"etag-del"')
    Test uses MagicMock so update_contact_vcard doesn't actually change ETags.
    The test asserts delete is called with the ORIGINAL etag-del, which is the bug.
    The test passes because mocks don't enforce ETag consistency.
  implication: Test does not catch this bug because mocks bypass real ETag behavior

## Resolution

root_cause: |
  In apply_reset(), step 6 iterates ALL annotated contacts (including contacts_to_delete)
  and PUTs updated vCards via update_contact_vcard(contact.href, contact.etag, vcard_bytes).
  This changes the server-side ETag. The new ETag IS returned by update_contact_vcard()
  but is DISCARDED (line 358 does not capture the return value). Step 7 then calls
  delete_contact(contact.href, contact.etag) using the ORIGINAL plan-time ETag, which
  is now stale. The server rejects the DELETE with 412 Precondition Failed.

fix: (diagnosis only - not applied)
verification: (diagnosis only)
files_changed: []
