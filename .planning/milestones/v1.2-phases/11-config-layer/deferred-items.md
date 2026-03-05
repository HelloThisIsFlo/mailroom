# Deferred Items - Phase 11

## Pre-existing: Sieve guidance test boundary parsing issue

**Found during:** Plan 11-02, Task 1
**File:** tests/test_sieve_guidance.py::TestGenerateGuidanceDefaultMode::test_add_to_inbox_no_archive
**Issue:** The test's section parser for finding the "Imbox" section bleeds into the Person child section (which contains "Archive"), causing a false assertion failure. This is pre-existing (not caused by Plan 02 changes) -- it comes from unstaged changes in sieve_guidance.py.
**Impact:** Does not affect screener workflow or config tests. Likely to be addressed by Plan 11-03 (sieve guidance updates).
