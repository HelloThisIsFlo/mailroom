---
date: 2026-03-04
status: diagnosis-complete
severity: major-gap
title: Undocumented Dependency on Fastmail's REV Field for User-Modification Detection
---

# Diagnosis: Undocumented REV Field Dependency

## Executive Summary

The `_is_user_modified()` function in `src/mailroom/reset/resetter.py` relies on an implicit mechanism to detect when users modify contacts: it checks for extra vCard fields that Fastmail has NOT been documented as adding. **However, when Fastmail itself adds the REV (revision timestamp) field upon any contact edit through their UI, this field triggers the detection mechanism.** This works correctly but represents an undocumented, implicit assumption about Fastmail's behavior that is not tested.

**Root Cause:** The detection mechanism was designed to catch user-added fields (TEL, ADDR, PHOTO, etc.), but Fastmail's automatic REV field addition during user edits is relied upon implicitly—there is no explicit test or documentation that this behavior is the actual mechanism enabling detection.

---

## The Mechanism

### How `_is_user_modified()` Works

**File:** `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/reset/resetter.py` (lines 24-59)

```python
MAILROOM_MANAGED_FIELDS = {
    "version", "uid", "fn", "n", "email", "note", "org", "prodid",
}
_SYSTEM_FIELD_PREFIXES = ("x-addressbookserver-",)

def _is_user_modified(vcard_data: str) -> bool:
    """Detect whether a contact has been modified by the user."""
    card = vobject.readOne(vcard_data)
    content_keys = {k.lower() for k in card.contents.keys()}
    user_fields = {
        k for k in content_keys
        if not any(k.startswith(p) for p in _SYSTEM_FIELD_PREFIXES)
    }
    extra = user_fields - MAILROOM_MANAGED_FIELDS  # ← Key check
    if extra:
        return True
    if len(card.contents.get("email", [])) > 1:
        return True
    return False
```

**Logic:**
1. Parse vCard to get all field names
2. Filter out system fields (x-addressbookserver-*)
3. Check if any fields exist outside `MAILROOM_MANAGED_FIELDS`
4. Return `True` if extra fields found OR multiple EMAIL entries

### The Implicit Assumption: REV Field Presence

**The Gap:** When a user edits a contact through Fastmail's web UI (e.g., adds a phone number), Fastmail adds:
- `REV` field (revision timestamp)
- Plus any user-added fields (TEL, PHOTO, etc.)

**Current Behavior:** The `REV` field is NOT in `MAILROOM_MANAGED_FIELDS`, so when `extra = user_fields - MAILROOM_MANAGED_FIELDS` is calculated, `REV` is included in `extra`. Since `extra` is non-empty, the function returns `True` (user-modified).

**The Problem:** This works, but it's a **happy accident**:
- No test explicitly validates that `REV` triggers modification detection
- No documentation explains that Fastmail's automatic `REV` field is the relied-upon signal
- If Fastmail stops adding `REV` (or adds it conditionally), detection breaks without clear explanation
- A user editing only the name field (without explicit additions like TEL) would still trigger detection because of `REV`

---

## Evidence of the Gap

### 1. Planning Documents Acknowledge the Risk

**File:** `.planning/phases/14-contact-provenance-tracking-for-clean-reset/14-UAT.md` (line 93-101)

User UAT report flagged this as a **major gap**:

```yaml
- truth: "Fastmail adds REV field on contact edit — user-modification detection depends on this implicitly"
  status: failed
  reason: "User reported: Happy accident that REV field triggers _is_user_modified().
           Any undocumented relied-upon behavior is a major gap. Needs explicit test
           and human integration test validating Fastmail adds REV on edit."
  severity: major
```

### 2. Unit Tests Cover Field Detection But NOT REV Explicitly

**File:** `/Users/flo/Work/Private/Dev/Services/mailroom/tests/test_resetter.py` (lines 711-782)

Current tests in `TestIsUserModified`:

| Test | What It Tests | REV Coverage |
|------|---------------|--------------|
| `test_unmodified_returns_false` | vCard with only MAILROOM_MANAGED_FIELDS | No — doesn't include REV |
| `test_tel_field_returns_true` | vCard with TEL added by user | No — REV not in test vCard |
| `test_additional_email_returns_true` | vCard with 2+ EMAIL fields | No — REV not in test vCard |
| `test_adr_returns_true` | vCard with ADR (address) | No — REV not in test vCard |
| `test_apple_system_fields_not_treated_as_user` | x-addressbookserver-* ignored | No — verifies system exclusion, not REV |

**Gap:** No test creates a vCard with ONLY REV added (simulating Fastmail's behavior), confirming REV alone triggers `True`.

### 3. Research & Planning Documents Don't Explicitly Include REV

**File:** `.planning/phases/14-contact-provenance-tracking-for-clean-reset/14-RESEARCH.md` (lines 188-231)

The research document lists user-modification indicators:
- TEL (phone number)
- ADR (address)
- URL (website)
- PHOTO (image)
- BDAY (birthday)
- TITLE (job title)
- NICKNAME
- Additional EMAIL entries
- Any X- custom properties

**Gap:** No mention of `REV` as a relied-upon Fastmail behavior.

### 4. Helper Script Doesn't Mention REV

**File:** `.research/contact-modification/inspect_vcard.py` (lines 30-32)

The helper script to inspect real vCards uses the same `MAILROOM_MANAGED_FIELDS` set. **While this script would show REV in actual Fastmail contacts, the documentation doesn't explain its role.**

---

## Impact Analysis

### If REV Detection Were to Break

**Scenario:** Fastmail changes its behavior and stops adding REV on contact edits.

**Current State:**
- User edits contact name (no other fields) through Fastmail UI
- vCard now has: VERSION, UID, FN (updated), N (updated), EMAIL, NOTE, ORG, PRODID, **REV**
- `_is_user_modified()` returns `True` ✓ (correct: user did modify)

**If REV Disappears:**
- User edits contact name through Fastmail UI
- vCard now has: VERSION, UID, FN (updated), N (updated), EMAIL, NOTE, ORG, PRODID (NO REV)
- `_is_user_modified()` returns `False` ✗ (wrong: user DID modify, but detection misses it)
- **Result:** Contact stays in provenance group and gets deleted during reset (data loss)

### What Should Actually Trigger "Modified"

**Design Intent (from RESEARCH.md):**
> "Extra fields that Mailroom never creates" (TEL, ADR, URL, PHOTO, BDAY, TITLE, NICKNAME, etc.)

**Current Implementation:**
> Any field not in MAILROOM_MANAGED_FIELDS (which includes REV implicitly via Fastmail behavior)

**The Mismatch:** The implementation accidentally catches REV instead of deliberately catching user-added fields.

---

## What's Missing

### 1. Explicit REV Test (Unit)

**Where:** `tests/test_resetter.py`, class `TestIsUserModified`

**Missing Test:**
```python
def test_rev_field_alone_returns_true(self) -> None:
    """Contact with only REV field added by Fastmail IS user-modified."""
    vcard = self._make_vcard("REV:20260304T150000Z\r\n")
    assert _is_user_modified(vcard) is True
```

**Why:** Validates that Fastmail's automatic REV addition correctly triggers modification detection.

**Note:** This test documents the assumption that `REV` is the mechanism, not an accident.

### 2. REV Field Documentation in Code

**Where:** `src/mailroom/reset/resetter.py`, docstring for `_is_user_modified()`

**Current Docstring (lines 31-45):**
```python
def _is_user_modified(vcard_data: str) -> bool:
    """Detect whether a contact has been modified by the user.

    Compares vCard fields against what Mailroom creates. Extra fields
    (phone, address, photo, etc.) indicate user modification. Multiple
    EMAIL entries also indicate user modification.

    Apple system fields (x-addressbookserver-*) are ignored.

    Args:
        vcard_data: Raw vCard string.

    Returns:
        True if the contact has user-added fields beyond Mailroom's set.
    """
```

**Gap:** No mention of REV field or Fastmail's behavior.

**Missing Documentation:**
```python
def _is_user_modified(vcard_data: str) -> bool:
    """Detect whether a contact has been modified by the user.

    Compares vCard fields against what Mailroom creates. Extra fields
    (phone, address, photo, etc.) indicate user modification. Multiple
    EMAIL entries also indicate user modification.

    Note: When users edit contacts in Fastmail's UI, Fastmail adds a
    REV (revision timestamp) field. This field is not in MAILROOM_MANAGED_FIELDS,
    so its presence indicates modification. This is the primary signal
    for detecting user edits in Fastmail.

    Apple system fields (x-addressbookserver-*) are ignored.

    Args:
        vcard_data: Raw vCard string.

    Returns:
        True if the contact has user-added fields (including REV from Fastmail edits)
        beyond Mailroom's managed set.
    """
```

### 3. MAILROOM_MANAGED_FIELDS Comment Clarification

**Where:** `src/mailroom/reset/resetter.py`, lines 24-26

**Current Comment:**
```python
# Fields that Mailroom sets on contacts it creates/manages
MAILROOM_MANAGED_FIELDS = {
    "version", "uid", "fn", "n", "email", "note", "org", "prodid",
}
```

**Gap:** Doesn't explain what's NOT included and why (e.g., REV).

**Missing Clarification:**
```python
# Fields that Mailroom sets on contacts it creates/manages.
# Does NOT include REV (revision timestamp) — Fastmail adds this on any edit,
# making it the primary signal for user modification detection.
# Does NOT include system fields (x-addressbookserver-*), which are handled by
# _SYSTEM_FIELD_PREFIXES exclusion.
MAILROOM_MANAGED_FIELDS = {
    "version", "uid", "fn", "n", "email", "note", "org", "prodid",
}
```

### 4. Human Integration Test for REV Behavior

**Where:** `human-tests/` (new or updated test)

**What's Missing:** A test that:
1. Creates a contact via Mailroom triage (ensures it's added to provenance group)
2. Manually edits the contact in Fastmail's web UI (just changing a name field, no TEL/ADR)
3. Runs `mailroom reset --apply` in dry-run mode
4. Verifies the contact is classified as "modified" (in `contacts_to_warn`, not `contacts_to_delete`)

**Why:** Confirms Fastmail adds REV on edit and that detection catches it.

**Test Name:** `test_18_user_modified_via_fastmail_edit.py` (or similar)

---

## Artifacts Affected

| File | Issue | Severity |
|------|-------|----------|
| `src/mailroom/reset/resetter.py` | Missing documentation that REV field is the relied-upon signal; docstring doesn't explain MAILROOM_MANAGED_FIELDS exclusion rationale | Major |
| `tests/test_resetter.py` | No test explicitly validating that REV field triggers `True` return | Major |
| `.research/contact-modification/inspect_vcard.py` | No documentation that REV should be explained | Minor |
| `human-tests/` | No integration test verifying Fastmail adds REV on edit and detection catches it | Major |

---

## Recommended Fixes (Summary)

1. **Add unit test:** `test_rev_field_alone_returns_true()` in `tests/test_resetter.py`
2. **Update docstring:** Clarify in `_is_user_modified()` that REV field is the primary signal
3. **Update constant comment:** Explain in `MAILROOM_MANAGED_FIELDS` why REV is excluded
4. **Add human integration test:** Verify Fastmail adds REV on edit and detection works correctly

---

## Related Issues

- Phase 14 UAT Gap #8 (line 93-101 of 14-UAT.md)
- Phase 14 Verification: No gaps flagged, but this analysis uncovers undocumented assumption

---

## References

- **Main Implementation:** `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/reset/resetter.py` lines 24-59
- **Unit Tests:** `/Users/flo/Work/Private/Dev/Services/mailroom/tests/test_resetter.py` lines 711-782
- **Research:** `.planning/phases/14-contact-provenance-tracking-for-clean-reset/14-RESEARCH.md` lines 188-231
- **UAT Report:** `.planning/phases/14-contact-provenance-tracking-for-clean-reset/14-UAT.md` lines 93-101
- **Helper Script:** `.research/contact-modification/inspect_vcard.py`
