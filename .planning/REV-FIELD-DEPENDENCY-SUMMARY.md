---
diagnosis_type: implicit-dependency-analysis
date: 2026-03-04
severity: major
status: diagnosis-complete
---

# REV Field Dependency: Structured Diagnosis

## Root Cause

**The `_is_user_modified()` function in `src/mailroom/reset/resetter.py` relies on an implicit, undocumented assumption that Fastmail adds a REV (revision timestamp) field whenever a user edits a contact through the Fastmail UI.** This works correctly in practice but represents a "happy accident" — the mechanism was not explicitly designed or tested, and no documentation explains that REV is the relied-upon signal for detecting user modifications.

**Core Mechanism:**
- `MAILROOM_MANAGED_FIELDS` includes: version, uid, fn, n, email, note, org, prodid
- `MAILROOM_MANAGED_FIELDS` does NOT include: rev
- `_is_user_modified()` returns `True` if any vCard field exists outside `MAILROOM_MANAGED_FIELDS`
- When Fastmail adds `REV` on user edit, that field is "extra" and triggers `True` ✓
- But there's no test or documentation that validates this is the actual mechanism

---

## Artifacts Needing Test Coverage

### 1. Unit Test Gap

**File:** `/Users/flo/Work/Private/Dev/Services/mailroom/tests/test_resetter.py`

**Current State:**
- Lines 711-782: Class `TestIsUserModified` with 9 tests
- Tests cover: TEL, ADR, URL, BDAY, TITLE, NICKNAME, PHOTO, multiple EMAIL, Apple system fields
- **Missing:** No test that creates a vCard with ONLY REV added (no other user fields)

**What's Needed:**
- Test case: `test_rev_field_alone_returns_true()`
- Creates minimal vCard with only REV added
- Validates `_is_user_modified(vcard)` returns `True`
- Documents that REV alone triggers detection

### 2. Code Documentation Gap

**File:** `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/reset/resetter.py`

**Current State:**
- Lines 24-26: `MAILROOM_MANAGED_FIELDS` set with no explanation
- Lines 28: `_SYSTEM_FIELD_PREFIXES` comment mentions system fields
- Lines 31-45: `_is_user_modified()` docstring explains general detection but not REV

**What's Needed:**
- Update `MAILROOM_MANAGED_FIELDS` comment: Explain why REV is intentionally excluded
- Update `_is_user_modified()` docstring: Document that REV field presence from Fastmail edits is the primary user-modification signal
- Add note about Fastmail behavior (REV added on any contact edit in their UI)

### 3. Human Integration Test Gap

**File:** `human-tests/` directory

**Current State:**
- Test suite runs 17+ human integration tests (test_1_auth through test_17_retriage)
- None explicitly validate that Fastmail adds REV or that `_is_user_modified()` detects it

**What's Needed:**
- New test: `test_18_rev_field_user_modification.py` or similar
- Steps:
  1. Create contact via Mailroom (email from unknown sender to Screener, apply triage label)
  2. Verify contact is added to provenance group
  3. Manually edit contact in Fastmail UI (e.g., change display name only — no TEL/ADR)
  4. Run `mailroom reset --apply` (dry-run first)
  5. Verify contact is classified as "modified" (in contacts_to_warn, not contacts_to_delete)
  6. Inspect actual vCard to confirm REV field is present
- Validates end-to-end: Fastmail adds REV → detection catches it → reset classifies correctly

### 4. Research Documentation Gap

**File:** `.research/contact-modification/inspect_vcard.py`

**Current State:**
- Lines 29-33: `MAILROOM_MANAGED_FIELDS` defined, same as resetter.py
- Used for manual vCard inspection, but no output explanation of REV

**What's Needed:**
- Update script output to explicitly call out REV field when present
- Add comment explaining REV significance for modification detection
- Update usage documentation at top of file to mention REV field

---

## Missing Coverage Details

### Unit Test Coverage

| Scenario | Current | Missing |
|----------|---------|---------|
| vCard with only Mailroom-managed fields | ✓ Tested (test_unmodified_returns_false) | - |
| vCard with user-added TEL field | ✓ Tested (test_tel_field_returns_true) | - |
| vCard with user-added PHOTO field | ✓ Tested (test_photo_returns_true) | - |
| vCard with multiple EMAIL entries | ✓ Tested (test_additional_email_returns_true) | - |
| vCard with system x-addressbookserver-* fields | ✓ Tested (test_apple_system_fields_not_treated_as_user) | - |
| **vCard with ONLY REV field added (Fastmail behavior)** | ✗ **MISSING** | **TEST_REV_FIELD_ALONE** |
| vCard with REV + user-added TEL (real scenario) | ✗ **MISSING** | **TEST_REV_WITH_USER_FIELDS** |

### Human Integration Test Coverage

| Scenario | Current | Missing |
|----------|---------|---------|
| Fastmail adds REV on contact edit | Not tested | `test_18_rev_field_user_modification.py` |
| Detection correctly identifies REV as modification signal | Not tested | Part of test_18 |
| Reset classifies REV-only contacts as modified (not deleted) | Not tested | Part of test_18 |

### Documentation Coverage

| Element | Current | Missing |
|---------|---------|---------|
| Function docstring for `_is_user_modified()` | Generic explanation | REV-specific behavior documented |
| Constant comment for `MAILROOM_MANAGED_FIELDS` | Minimal comment | Explanation of excluded fields (REV, system fields) |
| Code comments near `_is_user_modified()` logic | None | Comment explaining why REV indicates modification |
| Research script documentation | Basic usage | REV field explanation in output |

---

## Severity & Impact Assessment

### Why This is a Major Gap

1. **Undocumented Assumption:** The entire user-modification detection system relies on Fastmail's REV field behavior, but this is never mentioned in code or tests.

2. **Brittle Dependency:** If Fastmail changes (stops adding REV, or changes when it's added), detection breaks silently—there's no explicit check that validates the assumption.

3. **False Sense of Coverage:** Unit tests pass and cover various user-added fields (TEL, PHOTO, etc.), creating the false impression that the mechanism is fully tested. But the actual relied-upon field (REV) is not tested.

4. **Maintenance Risk:** Future developers might remove REV from `MAILROOM_MANAGED_FIELDS` thinking it's unrelated to the detection logic, breaking the mechanism without realizing why.

5. **Reset Data Loss Scenario:** If detection fails (e.g., because REV is missing), unmodified Mailroom-created contacts don't become "modified" and stay in provenance group → get deleted during reset → user loses contact data.

### Mitigation Priority

- **Immediate:** Add unit test for REV field detection
- **Soon:** Add human integration test for Fastmail REV behavior
- **Before next release:** Update code documentation

---

## Test Additions Needed

### Test 1: REV Field Unit Test

**Location:** `tests/test_resetter.py`, class `TestIsUserModified`

**Code:**
```python
def test_rev_field_alone_returns_true(self) -> None:
    """Contact with REV field added by Fastmail IS user-modified.

    REV is the revision timestamp field that Fastmail adds when a user
    edits a contact through their UI. This is the primary signal that
    the contact has been modified outside of Mailroom's control.
    """
    vcard = self._make_vcard("REV:20260304T150000Z\r\n")
    assert _is_user_modified(vcard) is True
```

**Why:** Documents that REV alone triggers modification detection. Validates the implicit assumption.

### Test 2: REV + User Field Unit Test

**Location:** `tests/test_resetter.py`, class `TestIsUserModified`

**Code:**
```python
def test_rev_and_user_field_returns_true(self) -> None:
    """Contact with both REV and user-added field IS user-modified."""
    vcard = self._make_vcard(
        "REV:20260304T150000Z\r\n"
        "TEL;TYPE=CELL:+1234567890\r\n"
    )
    assert _is_user_modified(vcard) is True
```

**Why:** Validates real-world scenario where user edits trigger both REV and explicit field changes.

### Test 3: Human Integration Test for REV Detection

**Location:** `human-tests/test_18_rev_field_user_modification.py` (new file)

**Structure:**
```python
"""
Test that Fastmail adds REV field on contact edit,
and _is_user_modified() correctly detects it.

This is a human integration test that requires real Fastmail account.
"""

def test_fastmail_adds_rev_on_edit():
    # 1. Triage unknown sender -> creates contact + adds to provenance group
    # 2. Manually edit contact in Fastmail (change name only)
    # 3. Fetch updated vCard via CardDAV
    # 4. Verify REV field exists
    # 5. Run _is_user_modified(vcard) -> should return True
    # 6. Run reset in dry-run mode -> contact should appear in contacts_to_warn

def test_reset_respects_rev_modified_detection():
    # 1. Create contact
    # 2. Manually edit in Fastmail
    # 3. Inspect vCard to confirm REV present
    # 4. Run reset --apply
    # 5. Verify contact remains in Fastmail (not deleted)
    # 6. Verify contact removed from provenance group
```

---

## Implementation Roadmap

### Phase 1: Document the Assumption (Immediate)

1. Add comment to `MAILROOM_MANAGED_FIELDS` explaining REV exclusion
2. Update `_is_user_modified()` docstring with REV field information
3. Create or update `.planning/DIAGNOSIS-REV-FIELD-DEPENDENCY.md`

### Phase 2: Add Unit Tests (Next Commit)

1. Add `test_rev_field_alone_returns_true()`
2. Add `test_rev_and_user_field_returns_true()`
3. Run full test suite to verify green
4. Commit with message: "test(resetter): add explicit REV field detection tests"

### Phase 3: Add Human Integration Test (Next Sprint)

1. Create `human-tests/test_18_rev_field_user_modification.py`
2. Document test prerequisites (Fastmail account, provisioned contact groups)
3. Add to test run order in documentation
4. Run and verify before merging

---

## Files Modified

### For Unit Tests
- `/Users/flo/Work/Private/Dev/Services/mailroom/tests/test_resetter.py`
  - Add 2 new test methods to `TestIsUserModified` class
  - ~30 lines added

### For Code Documentation
- `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/reset/resetter.py`
  - Update `MAILROOM_MANAGED_FIELDS` comment (3-5 lines)
  - Update `_is_user_modified()` docstring (4-6 lines added)

### For Human Integration Testing
- `/Users/flo/Work/Private/Dev/Services/mailroom/human-tests/test_18_rev_field_user_modification.py` (new)
  - ~80-100 lines

### For Documentation
- `.planning/DIAGNOSIS-REV-FIELD-DEPENDENCY.md` (created)
- `.planning/REV-FIELD-DEPENDENCY-SUMMARY.md` (this file)

---

## References

- **Main Implementation:** `src/mailroom/reset/resetter.py` lines 24-59
- **Current Tests:** `tests/test_resetter.py` lines 711-782 (TestIsUserModified class)
- **UAT Gap Report:** `.planning/phases/14-contact-provenance-tracking-for-clean-reset/14-UAT.md` lines 93-101
- **Research Docs:** `.planning/phases/14-contact-provenance-tracking-for-clean-reset/14-RESEARCH.md` lines 188-231
- **vCard Inspection Tool:** `.research/contact-modification/inspect_vcard.py`

---

## Validation Checklist

- [ ] Unit tests added for REV field detection
- [ ] Tests pass locally (pytest tests/test_resetter.py::TestIsUserModified -v)
- [ ] Code comments updated in resetter.py
- [ ] Docstring updated for _is_user_modified()
- [ ] Human integration test created (test_18)
- [ ] Human integration test run successfully against real Fastmail account
- [ ] Full test suite passes (pytest tests/ -v)
- [ ] Documentation files created/updated
- [ ] Commit message references this diagnosis

