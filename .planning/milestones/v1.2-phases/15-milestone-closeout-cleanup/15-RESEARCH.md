# Phase 15: Milestone Closeout & Cleanup - Research

**Researched:** 2026-03-05
**Domain:** Documentation finalization, dead code removal, integration consistency, test isolation
**Confidence:** HIGH

## Summary

Phase 15 is a cleanup phase that addresses six specific gaps identified in the v1.2 milestone audit. All changes are well-scoped with precise file locations and known fixes. There is no new feature work -- every task either corrects an inconsistency, removes dead code, updates documentation artifacts, or finalizes WIP content into production documentation.

The documentation work (WIP.md finalization) is the largest effort. It involves creating a new `docs/workflow.md`, rewriting `docs/config.md` for the YAML-based config system, updating `docs/architecture.md` to reflect the full v1.2 system, and removing `docs/WIP.md`. The code changes are surgical: a one-line parameter addition in `resetter.py`, a one-line mock addition in test code, removal of two dead methods and their test classes, and two text edits in REQUIREMENTS.md.

**Primary recommendation:** Split into two plans -- one for all code/test fixes (fast, surgical) and one for documentation finalization (larger, writing-intensive).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Create `docs/workflow.md` from `docs/WIP.md` content -- comprehensive triage workflow reference
- Rewrite `docs/config.md` for config.yaml (YAML categories, add_to_inbox, parent, contact_type); keep credentials section (still env vars). Old env-var config docs are replaced entirely.
- Update `docs/architecture.md` to cover the full system: triage pipeline, re-triage, contact provenance tracking, and the reset CLI. Update the mermaid diagram to reflect parent/child categories and label scanning.
- Tone: open-source ready -- explain concepts, include examples, provide context for decisions. Written as if someone else might read it.
- Remove `docs/WIP.md` after content is integrated (WIP banner no longer needed)
- `run_reset()` in `resetter.py` must pass `infrastructure_groups=[settings.mailroom.provenance_group]` to `validate_groups()`, matching the `__main__.py` triage startup path
- Add `monkeypatch.setattr(resetter_mod, "configure_logging", lambda level: None)` in `TestRunResetConfirmation._run_reset_with_mocks()` to prevent structlog globally rebinding `PrintLoggerFactory`
- Remove `_get_destination_mailbox_ids()` from `screener.py` and its tests
- Remove `batch_move_emails()` from `jmap.py` and its tests
- Update REQUIREMENTS.md: RTRI-05 checkbox from `[ ]` to `[x]`, status from Pending to Complete
- Align RTRI-04 wording between REQUIREMENTS.md and code (docs say "Added to/Moved from", code uses "Triaged to/Re-triaged to")

### Claude's Discretion
- Exact structure and section ordering within workflow.md
- How to organize the architecture.md mermaid diagram (single vs multi-diagram)
- Level of detail in config.md examples
- Whether to update docs/index.html to reference new workflow.md

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CLOSE-01 | `docs/WIP.md` finalized into proper documentation and integrated into `docs/` at end of milestone | WIP.md content mapped to three target docs (workflow.md, config.md, architecture.md); source material analyzed; existing docs structure documented |
</phase_requirements>

## Standard Stack

This phase requires no new libraries. All work uses existing project tooling.

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| pytest | existing | Test verification after dead code removal | Already in project |
| Python | existing | Source edits in screener.py, jmap.py, resetter.py | Already in project |
| Markdown | N/A | Documentation writing | Project docs format |
| Mermaid | N/A | Architecture diagrams in architecture.md | Already used in docs |

## Architecture Patterns

### Existing Documentation Structure
```
docs/
  architecture.md   # System overview + mermaid diagram (needs updating)
  config.md         # Config reference (needs full rewrite for YAML)
  deploy.md         # Kubernetes deployment guide (no changes)
  FUTURE.md         # Strategic vision (no changes)
  index.html        # Landing page (discretionary update)
  WIP.md            # 213-line workflow reference (source material, to be removed)
```

### Documentation Content Flow

**WIP.md (source) -> Three targets:**

1. **workflow.md (NEW)** -- Comprehensive triage workflow reference
   - Core concepts: categories, child independence, add_to_inbox, destination_mailbox:Inbox ban
   - Default categories table with all 7 categories
   - Step-by-step triage walkthroughs (Person, Imbox, Billboard)
   - Deep nesting example
   - Sieve rule setup guidance
   - Re-triage workflow
   - Validation rules

2. **config.md (REWRITE)** -- Configuration reference
   - Keep credentials section (JMAP token, CardDAV username/password still env vars)
   - Replace all triage label / contact group env var tables with YAML config.yaml reference
   - Document `triage.categories` YAML structure: name, parent, contact_type, add_to_inbox
   - Document `mailroom:` section: label_error, label_warning, warnings_enabled, provenance_group
   - Document `polling:` and `logging:` sections
   - Include YAML examples

3. **architecture.md (UPDATE)** -- System architecture
   - Update mermaid diagram to show parent/child categories and label scanning
   - Add re-triage flow
   - Add contact provenance tracking
   - Add reset CLI description
   - Update component descriptions for ScreenerWorkflow (re-triage, reconciliation)
   - Update CardDAVClient description (provenance, delete_contact, group reassignment)
   - Update MailroomSettings description (YAML config, resolved_categories)

### Code Changes Map

| File | Change | Lines Affected |
|------|--------|---------------|
| `src/mailroom/reset/resetter.py:447` | Add `infrastructure_groups=[settings.mailroom.provenance_group]` to `validate_groups()` call | 1 line |
| `tests/test_resetter.py:~910` | Add `monkeypatch.setattr(resetter_mod, "configure_logging", lambda level: None)` in `_run_reset_with_mocks()` | 1 line |
| `src/mailroom/workflows/screener.py:461-481` | Remove `_get_destination_mailbox_ids()` method | ~20 lines |
| `src/mailroom/clients/jmap.py:507-561` | Remove `batch_move_emails()` method | ~55 lines |
| `tests/test_screener_workflow.py:432-474` | Remove `TestGetDestinationMailboxIds` class | ~43 lines |
| `tests/test_screener_workflow.py:1743-1750` | Remove `TestToPersonDestinationMailbox` class | ~8 lines |
| `tests/test_screener_workflow.py:1859-1906` | Remove `TestAddToInboxNotInherited` + `TestRootCategoryAddToInbox` classes | ~48 lines |
| `tests/test_jmap_client.py:986-1172` | Remove `TestBatchMoveEmails` class | ~187 lines |
| `.planning/REQUIREMENTS.md:41` | Change RTRI-05 from `[ ]` to `[x]` | 1 line |
| `.planning/REQUIREMENTS.md:40` | Update RTRI-04 wording to match code | 1 line |

### Dead Code Analysis

**`_get_destination_mailbox_ids()` in screener.py (lines 461-481):**
- Purpose: walks parent chain to collect destination mailbox IDs with add_to_inbox logic
- Status: tested but never called in production code
- Replaced by: inline equivalent logic in `_reconcile_email_labels()` (introduced in Phase 13 re-triage)
- Test classes to remove: `TestGetDestinationMailboxIds` (432-474), `TestToPersonDestinationMailbox` (1743-1750), `TestAddToInboxNotInherited` (1859-1878), `TestRootCategoryAddToInbox` (1881-1906)

**`batch_move_emails()` in jmap.py (lines 507-561):**
- Purpose: batch-move emails with chunking (remove source mailbox, add destination mailboxes)
- Status: tested but never called in production code
- Replaced by: inline `Email/set` patches in `_reconcile_email_labels()` (introduced in Phase 13 re-triage)
- Test class to remove: `TestBatchMoveEmails` (986-1172 in test_jmap_client.py)

### RTRI-04 Wording Alignment

**Current REQUIREMENTS.md (line 40):**
```
- [x] **RTRI-04**: Contact note captures triage history -- "Added to [group] on [date]" and "Moved from [old] to [new] on [date]"
```

**Actual code behavior (carddav.py):**
- New triage: `f"Triaged to {group_name} on {date.today().isoformat()}"` (line 453)
- Re-triage: `f"Re-triaged to {group_name} on {today}"` (line 897)

**Fix:** Update REQUIREMENTS.md RTRI-04 to:
```
- [x] **RTRI-04**: Contact note captures triage history -- "Triaged to [group] on [date]" and "Re-triaged to [group] on [date]"
```

### infrastructure_groups Consistency Fix

**The gap:** `resetter.py:447` calls `validate_groups()` without `infrastructure_groups`:
```python
carddav.validate_groups(settings.contact_groups + [settings.mailroom.provenance_group])
```

**The fix (match `__main__.py:128-131`):**
```python
carddav.validate_groups(
    settings.contact_groups + [settings.mailroom.provenance_group],
    infrastructure_groups=[settings.mailroom.provenance_group],
)
```

This ensures `check_membership()` in the reset path correctly excludes infrastructure groups, matching the triage startup path.

### structlog Cross-Contamination Fix

**Root cause:** `_run_reset_with_mocks()` calls `run_reset()` which calls `configure_logging()`, which globally rebinds structlog's `PrintLoggerFactory` to live `sys.stderr`. After pytest's capsys closes that file handle, subsequent screener workflow tests fail with `ValueError: I/O operation on closed file`.

**The fix:** Add to `_run_reset_with_mocks()` after importing `resetter_mod` (around line 910):
```python
monkeypatch.setattr(resetter_mod, "configure_logging", lambda level: None)
```

This is the same pattern used elsewhere in the test suite for mocking out side-effecting setup functions.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Documentation structure | Custom doc generator | Plain markdown files in `docs/` | Project already uses flat markdown docs |
| Mermaid diagrams | ASCII art or image files | Mermaid code blocks in markdown | Already the project standard, renders on GitHub |

## Common Pitfalls

### Pitfall 1: Removing dead code that is actually called
**What goes wrong:** Deleting a method that has hidden callers.
**Why it happens:** Grep misses dynamic calls or string-based references.
**How to avoid:** Verify with `grep -r` for ALL references including string mentions. The milestone audit already confirmed these are dead -- but verify before removing.
**Warning signs:** Test failures after removal on methods OTHER than the removed test classes.

### Pitfall 2: Test class removal breaking test numbering/fixtures
**What goes wrong:** Removing test classes in the middle of a file can break shared fixtures if other tests depend on class ordering.
**Why it happens:** pytest fixture scoping can be sensitive to class boundaries.
**How to avoid:** Run full test suite after each removal. The test classes being removed (`TestGetDestinationMailboxIds`, `TestBatchMoveEmails`, etc.) use the `workflow` fixture which is shared -- removal should be safe since no other class depends on their existence.
**Warning signs:** Fixture-related errors in tests that previously passed.

### Pitfall 3: Structlog mock placement
**What goes wrong:** Adding the `configure_logging` mock in the wrong location within `_run_reset_with_mocks()`.
**Why it happens:** The mock must be set BEFORE `run_reset()` is called, not after.
**How to avoid:** Place the monkeypatch.setattr after `import mailroom.reset.resetter as resetter_mod` (line 910) and before the `run_reset(apply=True)` call.
**Warning signs:** The 96 cross-contamination failures persist after the fix.

### Pitfall 4: Config.md rewrite losing credential information
**What goes wrong:** The rewrite focuses on YAML categories and forgets the env var credentials section.
**Why it happens:** The CONTEXT.md says "rewrite for config.yaml" but credentials remain env vars.
**How to avoid:** Keep the credentials section (JMAP token, CardDAV username/password) as env var documentation. Only the triage/label/group configuration moves to YAML.
**Warning signs:** The new config.md has no mention of `MAILROOM_JMAP_TOKEN` etc.

### Pitfall 5: Dead code removal order within screener_workflow tests
**What goes wrong:** Removing test classes at different line offsets can cause line-number confusion if done piecemeal.
**Why it happens:** Three separate test classes reference `_get_destination_mailbox_ids` at different positions in the 2879-line file.
**How to avoid:** Remove all dead code test classes in a single edit pass, working from bottom to top (highest line numbers first): `TestRootCategoryAddToInbox` (1881-1906), `TestAddToInboxNotInherited` (1859-1878), `TestToPersonDestinationMailbox` (1743-1750), then `TestGetDestinationMailboxIds` (432-474).

## Code Examples

### Fix: resetter.py validate_groups call
```python
# Source: __main__.py:128-131 (the correct pattern)
carddav.validate_groups(
    settings.contact_groups + [settings.mailroom.provenance_group],
    infrastructure_groups=[settings.mailroom.provenance_group],
)
```

### Fix: _run_reset_with_mocks structlog mock
```python
# Source: milestone audit recommendation
# Add after line 910 (import mailroom.reset.resetter as resetter_mod)
monkeypatch.setattr(resetter_mod, "configure_logging", lambda level: None)
```

### RTRI-04 wording fix
```markdown
# Before:
- [x] **RTRI-04**: Contact note captures triage history -- "Added to [group] on [date]" and "Moved from [old] to [new] on [date]"

# After:
- [x] **RTRI-04**: Contact note captures triage history -- "Triaged to [group] on [date]" and "Re-triaged to [group] on [date]"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Env var config (MAILROOM_LABEL_TO_*) | YAML config.yaml with categories | Phase 11 | config.md still documents old env var approach |
| batch_move_emails() for email filing | Inline Email/set patches in _reconcile_email_labels() | Phase 13 | batch_move_emails() is dead code |
| _get_destination_mailbox_ids() for mailbox resolution | Inline logic in _reconcile_email_labels() | Phase 13 | _get_destination_mailbox_ids() is dead code |
| Fixed 4-category mermaid diagram | Needs update for 7 categories + parent/child + provenance | Phases 11-14 | architecture.md diagram is stale |

## Open Questions

1. **Whether to update docs/index.html**
   - What we know: index.html references 4 fixed destinations and env var config. The feature card says "Labels, contact groups, polling interval, destinations -- all customizable via environment variables."
   - What's unclear: User left this as Claude's discretion
   - Recommendation: Do NOT update index.html in this phase. It is a marketing landing page, not technical docs. The copy is deliberately simplified for new visitors. Updating it would expand scope without clear value for a cleanup phase.

2. **deploy.md references to config.md**
   - What we know: deploy.md (line 57) links to config.md: "See config.md for a full reference of every environment variable"
   - What's unclear: After config.md is rewritten, this link text may be inaccurate (config is now mostly YAML, not env vars)
   - Recommendation: Update the link text in deploy.md to say "See config.md for the full configuration reference" (drop "environment variable" specificity). This is a minimal change that keeps the cross-reference accurate.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | pyproject.toml |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLOSE-01 | WIP.md finalized into docs | manual-only | N/A (documentation content) | N/A |
| (infra_groups fix) | validate_groups gets infrastructure_groups | unit | `python -m pytest tests/test_resetter.py -x -q` | Existing tests cover call chain |
| (structlog fix) | No cross-contamination in full suite | integration | `python -m pytest tests/ -x -q` | Existing tests verify (96 failures should become 0) |
| (dead code) | Removed methods have no callers | unit | `python -m pytest tests/ -x -q` | Full suite must pass after removal |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green + 0 cross-contamination failures

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. No new tests needed; the phase REMOVES tests (dead code) and fixes test isolation (structlog mock).

## Sources

### Primary (HIGH confidence)
- `src/mailroom/reset/resetter.py:447` -- validate_groups call without infrastructure_groups (direct code inspection)
- `src/mailroom/__main__.py:128-131` -- correct validate_groups pattern (direct code inspection)
- `tests/test_resetter.py:905-959` -- _run_reset_with_mocks implementation (direct code inspection)
- `src/mailroom/workflows/screener.py:461-481` -- _get_destination_mailbox_ids dead code (direct code inspection)
- `src/mailroom/clients/jmap.py:507-561` -- batch_move_emails dead code (direct code inspection)
- `src/mailroom/clients/carddav.py:453,897` -- actual triage history wording (direct code inspection)
- `.planning/v1.2-MILESTONE-AUDIT.md` -- gap identification and evidence (audit document)
- `docs/WIP.md` -- 213-line source material for workflow.md (direct content)
- `docs/config.md` -- current config reference to be rewritten (direct content)
- `docs/architecture.md` -- current architecture doc to be updated (direct content)

## Metadata

**Confidence breakdown:**
- Code fixes (infra_groups, structlog, dead code): HIGH -- exact lines identified, patterns verified in codebase
- Documentation finalization: HIGH -- source material exists (WIP.md), target structure clear, existing docs provide format precedent
- REQUIREMENTS.md updates: HIGH -- exact text and line numbers identified

**Research date:** 2026-03-05
**Valid until:** 2026-04-05 (stable -- cleanup phase with no external dependencies)
