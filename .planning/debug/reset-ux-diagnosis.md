---
status: diagnosed
trigger: "Investigate UX gaps in the mailroom reset command"
created: 2026-03-04T00:00:00Z
updated: 2026-03-04T00:00:00Z
---

## ROOT CAUSE ANALYSIS: Reset Command UX Gaps

### Problem Summary

Two distinct UX issues identified:

1. **No progress indication during reset execution** - User sees nothing while potentially long-running operations occur (can take minutes with many emails/contacts)
2. **Dry-run vs apply mode not clearly indicated upfront** - User runs command but output doesn't immediately clarify whether changes will be applied or just previewed

---

## Issue 1: Missing Progress Feedback During Execution

### Root Cause

**Location:** `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/reset/resetter.py` lines 376-446

The `run_reset()` function executes the following sequence:

1. Load config
2. Connect JMAP client
3. Connect CardDAV client
4. Validate groups
5. **Call `plan_reset()`** (long-running: queries emails, fetches contacts, determines groups)
6. Print plan (if dry-run)
7. **Call `apply_reset()`** (long-running: 7-step cleanup - batches email operations, group removals, contact updates, deletions)
8. Print result

**Problem Details:**

- **Planning phase** (lines 435-436):
  - `plan_reset()` calls `jmap.query_emails()` for each managed mailbox (lines 168-170)
  - `carddav.list_all_contacts()` to fetch all contacts (line 174)
  - Multiple group membership queries (lines 182-188)
  - No output or progress indication during any of these
  - Could easily take 10-30 seconds with hundreds of emails

- **Apply phase** (lines 443):
  - `apply_reset()` executes 7 sequential steps (lines 286-371):
    - Step 1: Remove managed labels from emails (batch operations per mailbox)
    - Step 2: Remove warning/error labels from all emails
    - Step 3: Remove contacts from groups
    - Step 4: Apply warning labels to user-modified contact emails
    - Step 5: Remove warned contacts from provenance group
    - Step 6: Strip Mailroom notes from all annotated contacts (loops through all)
    - Step 7: Delete unmodified provenance contacts
  - No per-step or per-operation progress output
  - Loop-based operations at lines 287-293, 308-314, 340-360, 366-371 have no progress feedback
  - Could easily take 30-120 seconds depending on volume

- **Reporting function** (line 444):
  - `print_reset_report()` only prints AFTER all operations complete
  - User sees nothing during execution - silent terminal for potentially 1-2 minutes

**Evidence:**

- `src/mailroom/reset/resetter.py:376-446` - `run_reset()` has zero progress output between client connection and final report
- `src/mailroom/reset/reporting.py:10-29` - `print_reset_report()` is called as single final output
- No `click.echo()`, `click.progressbar()`, or similar used
- No logging output sent to stdout (structured logging configured but not visible to user)

**Comparison to setup command:**

- `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/setup/provisioner.py:257-270` follows identical dry-run/apply pattern
- BUT `apply_resources()` at lines 135-173 and 175-197 processes one resource at a time with quick feedback
- Still has same issue: no per-step progress during resource creation

---

## Issue 2: Dry-run vs Apply Mode Not Clearly Indicated Upfront

### Root Cause

**Location:** `/Users/flo/Work/Private/Dev/Services/mailroom/src/mailroom/cli.py` lines 39-46

The Click `reset` command:

```python
@cli.command()
@click.option("--apply", is_flag=True, default=False, help="Apply changes (default is dry-run)")
def reset(apply: bool) -> None:
    """Reset all Mailroom changes: clean contacts, un-label emails, empty groups."""
    from mailroom.reset.resetter import run_reset

    exit_code = run_reset(apply=apply)
    sys.exit(exit_code)
```

**Problem Details:**

- Help text says `(default is dry-run)` but user doesn't see this unless they run `--help`
- `run_reset()` function at line 376 receives the `apply` flag but never displays it
- User executes `python -m mailroom reset` with no indication whether they're in dry-run or apply
- Only at END of execution (after all operations, in final report) do they learn what happened
- Setup command has identical issue at `cli.py:29-36`

**Current flow:**

```
User: python -m mailroom reset

[silence for 30-120 seconds depending on operation size]

Output: [ONLY NOW shows what was reset]
```

**User's mental model gap:**

- User doesn't know immediately: "Am I seeing a preview or is this live?"
- User can't ctrl-c with confidence: "If I kill this, will it break something?"
- User has no feedback: "Is it hung? Did it crash? Is it still working?"

**Evidence:**

- `src/mailroom/reset/resetter.py:376-446` - `run_reset(apply)` parameter is used only at line 438 for conditional execution, never printed
- `src/mailroom/reset/reporting.py:10-29` - `print_reset_report()` called only after operations finish
- `src/mailroom/cli.py:40-46` - Click command provides no feedback about `--apply` flag
- Comparison: `setup` command at `cli.py:30-36` has identical issue

---

## Impact Assessment

### Severity
- **Progress feedback:** HIGH - Can appear to hang for 1-2 minutes
- **Mode indication:** HIGH - User uncertainty about whether changes are live or preview

### User Experience
1. User runs `python -m mailroom reset` without `--apply`
2. Terminal goes silent - user wonders if command hung
3. After 60+ seconds, final report appears showing all the dry-run plan
4. User re-runs with `--apply`
5. Again: long silence, appears to hang
6. Finally: report showing what was actually changed

### Comparison to Setup Command
- Setup command at `provisioner.py:257-270` has SAME issues
- But setup typically affects fewer resources (mailbox creation is fast)
- Reset affects potentially thousands of emails + hundreds of contacts = longer wait

---

## Artifacts Requiring Changes

### File 1: `src/mailroom/reset/resetter.py`

**Current state:**
- Line 376: `run_reset(apply: bool = False)` - entry point
- Lines 435-436: Silent `plan_reset()` call
- Lines 438-444: Conditional execute/report with no mode indication

**Issues:**
1. No upfront banner showing `DRY RUN` or `APPLY` mode
2. No progress output during `plan_reset()` phase
3. No progress output during `apply_reset()` phase (7 steps with no visibility)
4. No per-operation feedback in loops at:
   - 287-293: Email label removal
   - 308-314: Group membership removal
   - 340-360: Contact note stripping
   - 366-371: Contact deletion

### File 2: `src/mailroom/reset/reporting.py`

**Current state:**
- Line 10: `print_reset_report(plan_or_result, apply)` - final output only
- Lines 31-97: `_print_plan_report()` and `_print_apply_report()` - end-of-execution summaries

**Issues:**
1. No "mode banner" function to print at START (before operations)
2. Report functions only designed for end-of-execution output
3. No progress functions for intermediate feedback

### File 3: `src/mailroom/cli.py`

**Current state:**
- Lines 40-46: Reset command with `--apply` flag
- Click option provides help text but no runtime feedback

**Issues:**
1. No upfront indication of mode to user
2. Click command receives mode but passes silently to `run_reset()`

---

## Missing Components

### 1. Upfront Mode Banner

**What's needed:**
- Print immediately after client connections validate
- Show: "Running reset in DRY RUN mode" OR "Running reset in APPLY mode"
- Use color to distinguish: YELLOW for dry-run, RED for apply
- Optional: Show total counts discovered during planning before execution

**Where:** `reporting.py` - new function `print_reset_banner(apply: bool, plan: ResetPlan = None)`

### 2. Planning Phase Progress

**What's needed:**
- Show when starting to plan (before silence)
- Per-mailbox progress: "Querying mailbox 1/5: Feed"
- Per-contact-group progress: "Loading contact groups..."
- Summary of what was found: "Found 247 emails, 18 contacts with Mailroom notes, 3 groups to empty"

**Where:** Inside `plan_reset()` or as wrapper in `run_reset()` with callbacks/logging visible to stdout

### 3. Apply Phase Progress (7 steps)

**What's needed:**
- Per-step banner: "Step 1/7: Removing managed labels from emails..."
- Per-operation feedback for loops:
  - "Removing labels from mailbox 1/4 (287 emails)..."
  - "Removing contacts from groups: 18/18 complete"
  - "Stripping notes from contacts: 18/18 complete"
  - "Deleting unmodified contacts: 5/5 complete"

**Where:** Inside `apply_reset()` with progress output at key points

### 4. Error Handling with Progress Context

**What's needed:**
- If error occurs mid-operation, show which step failed
- Show partial results up to error point
- Don't lose progress context if exception interrupts flow

**Where:** Both `apply_reset()` error handling and `run_reset()` exception wrapper

---

## Recommended Changes Summary

| File | Component | Change Type | Priority |
|------|-----------|-------------|----------|
| `src/mailroom/reset/reporting.py` | `print_reset_banner()` | NEW FUNCTION | HIGH |
| `src/mailroom/reset/reporting.py` | `print_step_progress()` | NEW FUNCTION | HIGH |
| `src/mailroom/reset/resetter.py` | `run_reset()` | Add banner before planning | HIGH |
| `src/mailroom/reset/resetter.py` | `plan_reset()` | Add progress callbacks | HIGH |
| `src/mailroom/reset/resetter.py` | `apply_reset()` | Add per-step headers + loop progress | HIGH |
| `src/mailroom/reset/resetter.py` | Step 1-7 loops | Add progress output to each | HIGH |

---

## Implementation Notes

### Design Principles

1. **Non-breaking:** All progress output goes to stdout/stderr via `print()`, not logging (users already see structured logs)
2. **Consistent:** Match colors and style from existing `setup/reporting.py`
3. **Informative:** Each progress line includes context (current/total, current item name where relevant)
4. **Optional:** Progress can be disabled with `--quiet` flag (future enhancement)

### Color Usage (from existing setup)
- GREEN: success/existing
- YELLOW: warning/planned
- RED: errors/critical operations (like delete)
- DIM: secondary info
- CYAN: headings/emphasis

### Example Output Flow

```
$ python -m mailroom reset
Checking Fastmail connection... ✓
Loading configuration... ✓

Running reset in DRY RUN mode

Planning reset...
  Querying mailbox 1/4: Feed
  Querying mailbox 2/4: Imbox
  Querying mailbox 3/4: Archive
  Querying mailbox 4/4: Spam Filter
  Fetching all contacts...
  Found: 247 emails • 18 annotated contacts • 3 groups

[Current behavior: ~30 sec silence, then report]

Email Labels to Clean
  ✗ Feed                            247 emails
  ✗ Imbox                           156 emails
...
```

With apply mode:
```
$ python -m mailroom reset --apply
...
Running reset in APPLY mode - THIS WILL MODIFY YOUR FASTMAIL ACCOUNT

Step 1/7: Removing managed labels from emails...
  Progress: 247 emails processed (4 failed)

Step 2/7: Cleaning system labels...
  Progress: 18 emails cleaned
...
```

---

## Conclusion

**Root causes identified:**
1. `run_reset()` executes silently without progress output during planning and apply phases
2. Mode (dry-run vs apply) not printed at command start, only implicit in final report
3. 7-step execution loop has no per-step visibility
4. Similar issues exist in setup command but less critical (faster operations)

**Impact:** User experiences 1-2 minute silent execution followed by final output, creating uncertainty about command state and operation type.

**Solution scope:** Add progress banners and per-operation feedback to `resetter.py` and `reporting.py` to provide real-time visibility into what's happening.
