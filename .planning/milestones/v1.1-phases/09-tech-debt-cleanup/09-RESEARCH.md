# Phase 9: Tech Debt Cleanup - Research

**Researched:** 2026-02-28
**Domain:** Codebase hygiene -- stale human tests, deployment artifact drift, dead code removal, helper deduplication
**Confidence:** HIGH

## Summary

Phase 9 addresses 11 tech debt items identified in the v1.1 milestone audit. All items are mechanical fixes with well-defined before/after states -- no new features, no architectural decisions, no library research needed. The work falls into five concrete buckets corresponding to the success criteria.

The most impactful items are the human test updates (7 files referencing deleted/renamed APIs) and the deployment artifact sync (.env.example and k8s/configmap.yaml still advertising 9 deleted env vars). These would cause real user confusion and test failures. The dead code removal (session_capabilities) and helper deduplication (ANSI colors) are minor cleanliness items.

**Primary recommendation:** Group work into 2-3 plans: (1) human test API migration, (2) deployment artifacts + dead code removal, (3) ANSI color extraction. All changes are safe, mechanical, and independently testable.

## Standard Stack

No new libraries needed. This phase only modifies existing files using existing patterns.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-settings | (existing) | Config model that human tests import | Already in use; settings API is the source of truth for fixes |

### Supporting
N/A -- no new dependencies for this phase.

### Alternatives Considered
N/A -- all changes are prescribed by the audit.

## Architecture Patterns

### Pattern 1: Human Test API Migration (Success Criteria 1)

**What:** 7 human test files reference two deleted/renamed APIs from the v1.0 config that were replaced in Phase 6.

**Old API (deleted in Phase 6):**
```python
# Deleted field -- raises AttributeError
settings.label_to_imbox           # was "@ToImbox"
settings.label_to_person          # was "@ToPerson"

# Renamed property -- dict[str, dict] -> dict[str, ResolvedCategory]
settings.label_to_group_mapping   # was dict with ["destination_mailbox"], ["group"] keys
```

**Current API (Phase 6+):**
```python
# Access specific labels through the resolved categories:
settings.label_to_category_mapping["@ToImbox"].label   # "@ToImbox"
settings.label_to_category_mapping["@ToPerson"].label  # "@ToPerson"

# Access category fields via attribute access (not dict keys):
settings.label_to_category_mapping["@ToImbox"].destination_mailbox  # "Inbox"
settings.label_to_category_mapping["@ToImbox"].contact_group        # "Imbox"

# Or use triage_labels for the list of all label names:
settings.triage_labels  # ["@ToImbox", "@ToFeed", "@ToPaperTrail", "@ToJail", "@ToPerson"]
```

**Files and exact changes needed:**

| File | Line(s) | Old Code | New Code |
|------|---------|----------|----------|
| `test_3_label.py` | 26 | `settings.label_to_imbox` | `settings.label_to_category_mapping["@ToImbox"].label` or simply hardcode `"@ToImbox"` (simpler for a human test) |
| `test_7_screener_poll.py` | 75 | `*[m["destination_mailbox"] for m in settings.label_to_group_mapping.values()]` | `*[c.destination_mailbox for c in settings.label_to_category_mapping.values()]` |
| `test_8_conflict_detection.py` | 84 | Same pattern as test_7 | Same fix |
| `test_9_already_grouped.py` | 83 | Same pattern as test_7 | Same fix |
| `test_9_already_grouped.py` | 133 | `settings.label_to_group_mapping[test_label]["group"]` | `settings.label_to_category_mapping[test_label].contact_group` |
| `test_10_retry_safety.py` | 82 | Same pattern as test_7 | Same fix |
| `test_11_person_contact.py` | 80 | Same pattern as test_7 | Same fix |
| `test_11_person_contact.py` | 226 | `settings.label_to_person` | `"@ToPerson"` (or via mapping) |
| `test_12_company_contact.py` | 80 | Same pattern as test_7 | Same fix |
| `test_12_company_contact.py` | 245 | `settings.label_to_imbox` | `"@ToImbox"` (or via mapping) |

**Pattern for the common mailbox resolution block (tests 7-12):**
```python
# OLD (will raise AttributeError):
all_mailboxes = list(dict.fromkeys([
    "Inbox",
    settings.screener_mailbox,
    settings.label_mailroom_error,
    *settings.triage_labels,
    *[m["destination_mailbox"] for m in settings.label_to_group_mapping.values()],
]))

# NEW (uses current API):
all_mailboxes = list(dict.fromkeys([
    "Inbox",
    settings.screener_mailbox,
    settings.label_mailroom_error,
    *settings.triage_labels,
    *[c.destination_mailbox for c in settings.label_to_category_mapping.values()],
]))
```

**Note:** `settings.required_mailboxes` already computes this exact deduplicated list (see `config.py:333-346`). The human tests could be simplified to just use `settings.required_mailboxes`, but that changes the test's explicit wiring which may be intentional for readability. The planner should decide -- either approach is correct.

### Pattern 2: Deployment Artifact Sync (Success Criteria 2 + 3)

**What:** `.env.example` and `k8s/configmap.yaml` still reference 9 deleted individual env vars from v1.0 config and have stale defaults.

**`.env.example` current state (stale):**
- Lines 22-23: `MAILROOM_POLL_INTERVAL=300` -- should be `60`
- Lines 28-34: Five `MAILROOM_LABEL_TO_*` vars -- should be removed
- Lines 38-40: `MAILROOM_LABEL_MAILROOM_ERROR`, `MAILROOM_LABEL_MAILROOM_WARNING`, `MAILROOM_WARNINGS_ENABLED` -- still valid
- Lines 44: `MAILROOM_SCREENER_MAILBOX` -- still valid
- Lines 47-50: Four `MAILROOM_GROUP_*` vars -- should be removed
- Missing: `MAILROOM_TRIAGE_CATEGORIES` JSON example
- Missing: `MAILROOM_DEBOUNCE_SECONDS`

**`.env.example` target state:**
```bash
# === Polling & Push ===
# MAILROOM_POLL_INTERVAL=60         # Seconds between fallback polls (default: 60)
# MAILROOM_DEBOUNCE_SECONDS=3       # SSE event debounce window (default: 3)

# === Triage Categories ===
# MAILROOM_TRIAGE_CATEGORIES='[{"name":"Imbox","destination_mailbox":"Inbox"},{"name":"Feed"},{"name":"Paper Trail"},{"name":"Jail"},{"name":"Person","parent":"Imbox","contact_type":"person"}]'
# Default categories (Imbox, Feed, Paper Trail, Jail, Person) are used when not set.
# See README for full category configuration options.
```

**`k8s/configmap.yaml` current state (stale):**
- Lines 7-21: Contains 9 deleted individual label/group vars plus `POLL_INTERVAL: "300"`
- Missing: `MAILROOM_TRIAGE_CATEGORIES`, `MAILROOM_DEBOUNCE_SECONDS`
- `MAILROOM_POLL_INTERVAL` should be `"60"`

**`k8s/configmap.yaml` target state:**
```yaml
data:
  MAILROOM_POLL_INTERVAL: "60"
  MAILROOM_DEBOUNCE_SECONDS: "3"
  MAILROOM_LOG_LEVEL: "info"
  MAILROOM_LABEL_MAILROOM_ERROR: "@MailroomError"
  MAILROOM_LABEL_MAILROOM_WARNING: "@MailroomWarning"
  MAILROOM_WARNINGS_ENABLED: "true"
  MAILROOM_SCREENER_MAILBOX: "Screener"
  # MAILROOM_TRIAGE_CATEGORIES: '<JSON>' # uncomment to override defaults
```

### Pattern 3: Dead Code Removal (Success Criteria 4)

**What:** `JMAPClient.session_capabilities` property and `_session_capabilities` instance variable are populated but never consumed in production code. Built for future sieve capability introspection that was descoped in Phase 7.

**Files to modify:**

| File | What to Remove |
|------|----------------|
| `src/mailroom/clients/jmap.py:30` | `self._session_capabilities: dict = {}` |
| `src/mailroom/clients/jmap.py:42-44` | `session_capabilities` property (3 lines) |
| `src/mailroom/clients/jmap.py:63` | `self._session_capabilities = data.get("capabilities", {})` |
| `tests/test_jmap_client.py:120-145` | `test_connect_stores_capabilities` and `test_session_capabilities_empty_before_connect` (2 tests, ~26 lines) |

**Impact:** None. The `connect()` method still stores `_api_url`, `_account_id`, `_download_url`, and `_event_source_url` which are all actively used. Only the capabilities dict is dead.

### Pattern 4: ANSI Color Helper Extraction (Success Criteria 5)

**What:** `reporting.py` and `sieve_guidance.py` each contain identical ANSI color helpers (`_GREEN`, `_YELLOW`, `_RED`, `_DIM`, `_RESET`, `_CYAN`, `_use_color()`, `_color()`). Extract into a shared module.

**Current duplication:**

`reporting.py` (lines 22-41):
```python
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"

def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _color(text: str, code: str) -> str:
    if not _use_color():
        return text
    return f"{code}{text}{_RESET}"
```

`sieve_guidance.py` (lines 19-34): Same code, but only defines `_CYAN` and `_RESET` (subset of constants).

**Recommended shared module location:** `src/mailroom/setup/colors.py`

This keeps it scoped to the `setup` package where both consumers live. No other modules outside `setup/` use color helpers (`__main__.py` and `screener.py` were checked -- no ANSI usage).

**Shared module should export:**
- Constants: `GREEN`, `YELLOW`, `RED`, `DIM`, `RESET`, `CYAN` (drop leading underscore since they become a public module API)
- Functions: `use_color() -> bool`, `color(text: str, code: str) -> str`

**Consumer updates:**
- `reporting.py`: Remove inline constants and functions, import from `colors.py`
- `sieve_guidance.py`: Remove inline constants and functions, import from `colors.py`

**Test impact:**
- `tests/test_provisioner.py` line 292: Tests `no_color_when_not_tty` -- import path unchanged (tests import `reporting`, not color helpers directly)
- `tests/test_sieve_guidance.py` lines 179-230: Tests color behavior -- import path unchanged (tests import `sieve_guidance`, not color helpers directly)
- No test changes needed since tests exercise the consumer modules, not the helpers directly
- Consider adding a small `tests/test_colors.py` for the shared module (basic smoke test for `use_color()` and `color()`)

### Anti-Patterns to Avoid
- **Changing human test behavior while fixing APIs:** The human tests should work identically after the fix -- same mailboxes resolved, same workflow exercised. Only the settings attribute access syntax changes.
- **Removing `.env.example` comments that are still valid:** `MAILROOM_LABEL_MAILROOM_ERROR`, `MAILROOM_LABEL_MAILROOM_WARNING`, `MAILROOM_WARNINGS_ENABLED`, and `MAILROOM_SCREENER_MAILBOX` are still valid config fields -- keep them.
- **Making color module too generic:** Keep it in `setup/` package. Don't put it in `core/` unless other packages need it (they don't).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mailbox list for human tests | Custom deduplication logic | `settings.required_mailboxes` | Already computed correctly in config.py; but check if the test intentionally shows explicit wiring |

**Key insight:** All five success criteria have explicit, mechanical transformations. There are no design decisions to make -- the audit prescribes exact before/after states.

## Common Pitfalls

### Pitfall 1: Missing a human test reference site
**What goes wrong:** Updating 6 of 7 files, missing one reference that still raises AttributeError at runtime.
**Why it happens:** Some files have multiple reference sites (test_9 has 2, test_11 has 2, test_12 has 3).
**How to avoid:** After all edits, run `grep -rn 'label_to_group_mapping\|label_to_imbox\|label_to_person' human-tests/` and verify zero matches.
**Warning signs:** Grep still finds matches after edits.

### Pitfall 2: k8s/configmap.yaml not matching .env.example
**What goes wrong:** One artifact is updated but the other is missed, causing deployment config to drift.
**Why it happens:** They are in different directories and easy to forget.
**How to avoid:** Update both in the same plan/task. Success criterion 3 explicitly requires they match.
**Warning signs:** Side-by-side comparison shows different env vars.

### Pitfall 3: Breaking existing tests when extracting colors
**What goes wrong:** Import path changes cause test failures.
**Why it happens:** Tests import the consumer modules, not the helpers -- but if the consumer module's re-export or internal wiring changes, tests may fail.
**How to avoid:** Run full test suite after extraction. Tests don't import color helpers directly, so as long as `_color()` and `_use_color()` still work in the consumer modules, tests pass.
**Warning signs:** `pytest` failures in `test_provisioner.py` or `test_sieve_guidance.py` after color extraction.

### Pitfall 4: Removing session_capabilities but leaving connect() line
**What goes wrong:** `self._session_capabilities = data.get("capabilities", {})` left in `connect()` after property is removed, creating an orphaned assignment.
**Why it happens:** Property removal is separate from the assignment in `connect()`.
**How to avoid:** Remove all three sites: init assignment, property, connect() assignment.
**Warning signs:** `grep -rn 'session_capabilities\|_session_capabilities' src/` shows remaining references.

## Code Examples

### Human test mailbox resolution (current API)
```python
# Source: src/mailroom/core/config.py lines 322-330
# label_to_category_mapping returns dict[str, ResolvedCategory]
# ResolvedCategory has: .name, .label, .contact_group, .destination_mailbox, .contact_type, .parent

mapping = settings.label_to_category_mapping
# Access destination mailbox:
for label, cat in mapping.items():
    print(f"{label} -> {cat.destination_mailbox} (group: {cat.contact_group})")

# Get a specific label's category:
imbox_cat = settings.label_to_category_mapping["@ToImbox"]
imbox_cat.label             # "@ToImbox"
imbox_cat.destination_mailbox  # "Inbox"
imbox_cat.contact_group     # "Imbox"
```

### Shared color module pattern
```python
# Source: extracted from src/mailroom/setup/reporting.py lines 22-41

import os
import sys

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"

def use_color() -> bool:
    """Return True if ANSI color should be used."""
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def color(text: str, code: str) -> str:
    """Wrap text in ANSI color if color is enabled."""
    if not use_color():
        return text
    return f"{code}{text}{RESET}"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 9 individual `MAILROOM_LABEL_*`/`MAILROOM_GROUP_*` env vars | Single `MAILROOM_TRIAGE_CATEGORIES` JSON env var | Phase 6 (v1.1) | Human tests, .env.example, k8s/configmap.yaml all need updating |
| `settings.label_to_group_mapping` (dict of dicts) | `settings.label_to_category_mapping` (dict of ResolvedCategory) | Phase 6 (v1.1) | Attribute access instead of dict key access |
| `settings.label_to_imbox` / `settings.label_to_person` (individual fields) | Removed -- use `label_to_category_mapping["@ToImbox"]` or hardcode | Phase 6 (v1.1) | Human tests 3, 11, 12 need updating |
| `MAILROOM_POLL_INTERVAL=300` | `poll_interval=60` (push primary, poll fallback) | Phase 8 (v1.1) | .env.example and k8s/configmap.yaml need updating |

## Open Questions

None. All five success criteria have clear, prescribed transformations. No ambiguity in what needs to change.

## Sources

### Primary (HIGH confidence)
- `src/mailroom/core/config.py` -- Current settings API (label_to_category_mapping, required_mailboxes, triage_labels)
- `src/mailroom/clients/jmap.py` -- session_capabilities property and _session_capabilities usage
- `src/mailroom/setup/reporting.py` -- ANSI color helpers (full implementation)
- `src/mailroom/setup/sieve_guidance.py` -- ANSI color helpers (subset)
- `src/mailroom/workflows/screener.py` -- Current usage of label_to_category_mapping (lines 303, 362)
- `.planning/v1.1-MILESTONE-AUDIT.md` -- Complete tech debt inventory with 11 items
- `human-tests/test_3_label.py` through `test_12_company_contact.py` -- All stale API references identified
- `.env.example` and `k8s/configmap.yaml` -- Current stale state verified
- `tests/test_jmap_client.py` -- Two tests for session_capabilities identified (lines 120-145)

## Metadata

**Confidence breakdown:**
- Human test fixes: HIGH -- exact old/new API verified against live config.py; all reference sites identified via grep
- Deployment artifacts: HIGH -- exact stale vars and correct replacements verified against current config.py defaults
- Dead code removal: HIGH -- session_capabilities confirmed unused outside its own property; 3 removal sites identified
- Color extraction: HIGH -- both files read in full; duplication confirmed; test impact analyzed (none)

**Research date:** 2026-02-28
**Valid until:** indefinite (all findings based on current codebase state, not external dependencies)
