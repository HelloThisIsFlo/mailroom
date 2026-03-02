# Phase 6: Deferred Items

## Out-of-Scope Discoveries

### human-tests/ reference old `label_to_group_mapping` API

**Found during:** 06-02 Task 2
**Files affected:**
- `human-tests/test_7_screener_poll.py`
- `human-tests/test_8_conflict_detection.py`
- `human-tests/test_9_already_grouped.py`
- `human-tests/test_10_retry_safety.py`
- `human-tests/test_11_person_contact.py`
- `human-tests/test_12_company_contact.py`

**Issue:** These files reference `settings.label_to_group_mapping` (dict access with `["destination_mailbox"]` etc.) which was renamed to `settings.label_to_category_mapping` (returns `ResolvedCategory` with attribute access). They will fail when run against the updated codebase.

**Fix needed:** Update all human-test files to use `label_to_category_mapping` with `ResolvedCategory` attribute access instead of dict key access. This is a mechanical change.
