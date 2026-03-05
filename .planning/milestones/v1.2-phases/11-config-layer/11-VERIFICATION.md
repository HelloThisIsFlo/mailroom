---
phase: 11-config-layer
verified: 2026-03-03T16:00:00Z
status: passed
score: 18/18 must-haves verified
re_verification:
  previous_status: passed
  previous_score: 16/16
  gaps_closed:
    - "CFG-02 catches destination_mailbox: Inbox case-insensitively with clear error"
    - "Sieve guidance output is clean and focused on UI instructions"
  gaps_remaining: []
  regressions: []
---

# Phase 11: Config Layer Verification Report

**Phase Goal:** Operators can configure inbox visibility independently of destination mailbox, and child categories resolve as fully independent categories that additively carry parent labels
**Verified:** 2026-03-03
**Status:** PASSED
**Re-verification:** Yes — after UAT gap closure (Plan 04)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | TriageCategory accepts add_to_inbox boolean defaulting to false | VERIFIED | `config.py:34` — `add_to_inbox: bool = False`; TestAddToInboxField passes |
| 2 | ResolvedCategory carries add_to_inbox field | VERIFIED | `config.py:56` — frozen dataclass field; TestResolvedCategoryAddToInbox passes |
| 3 | 7 default categories: Imbox (add_to_inbox=True), Feed, Paper Trail, Jail, Person (parent: Imbox), Billboard (parent: Paper Trail), Truck (parent: Paper Trail) | VERIFIED | `config.py:85-93`; TestDefaultFactory passes |
| 4 | Child categories resolve with own label, contact_group, destination_mailbox (no parent field inheritance) | VERIFIED | `config.py:227-248` — single-pass resolution; TestChildIndependence passes |
| 5 | destination_mailbox set to "Inbox", "inbox", "INBOX", or any case variant is rejected with helpful error pointing to add_to_inbox | VERIFIED | `config.py:193` — `resolved_mailbox.lower() == "inbox"`; 6 TestDestinationMailboxInboxRejected tests all pass (including lowercase, uppercase, derived-lowercase variants) |
| 6 | ValidationError from config loading shown as clean one-line message, not raw Pydantic traceback | VERIFIED | `__main__.py:105-109` — `except ValidationError as exc: print(f"Configuration error: {exc}", file=sys.stderr)` |
| 7 | Circular parent references detected and rejected | VERIFIED | `config.py:133-150`; TestValidationCircularParents passes |
| 8 | get_parent_chain walks from category up through ancestors | VERIFIED | `config.py:253-263`; TestGetParentChain passes |
| 9 | Triaging to a child category files emails to child + all ancestor destination mailboxes | VERIFIED | `screener.py:362-381`; TestGetDestinationMailboxIds passes |
| 10 | Triaging to a child category adds sender to child + all ancestor contact groups | VERIFIED | `screener.py:328-335`; TestAdditiveContactGroups passes |
| 11 | add_to_inbox on the triaged category (not ancestors) adds Inbox to mailbox list | VERIFIED | `screener.py:375` — checks `category.add_to_inbox` only; TestRootCategoryAddToInbox passes |
| 12 | add_to_inbox on a parent does NOT propagate to child triage | VERIFIED | `screener.py:375` — no chain walk for add_to_inbox; TestAddToInboxNotInherited passes |
| 13 | Sieve guidance shows all 7 categories grouped by parent with IMPORTANT Continue note | VERIFIED | `sieve_guidance.py:35-43`, no root-only filter; test_all_seven_categories_present passes (24 sieve tests total) |
| 14 | add_to_inbox categories show 2 actions (add label + continue, no archive); standard show 3 | VERIFIED | `sieve_guidance.py:64-69`; test_add_to_inbox_no_archive and test_standard_has_archive pass |
| 15 | Sieve guidance has no --ui-guide flag, no _build_ui_guide function, no commented sieve blocks | VERIFIED | `sieve_guidance.py` — no ui_guide anywhere; no fileinto/jmapquery commented blocks; cli.py and provisioner.py also clean |
| 16 | generate_sieve_guidance() takes only settings (no ui_guide parameter) | VERIFIED | `sieve_guidance.py:19` — `def generate_sieve_guidance(settings: MailroomSettings) -> str:` |
| 17 | Syntax highlighting: BOLD names, CYAN mailboxes, MAGENTA keywords | VERIFIED | `colors.py:12-14`; TestSyntaxHighlighting (5 tests) passes |
| 18 | config.yaml.example shows new defaults with add_to_inbox, independent children, Billboard, Truck | VERIFIED | Verified in initial report; no changes in Plan 04 |

**Score:** 18/18 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mailroom/core/config.py` | Case-insensitive CFG-02 check | VERIFIED | `resolved_mailbox.lower() == "inbox"` at line 193 |
| `src/mailroom/__main__.py` | Clean ValidationError catch at startup | VERIFIED | `except ValidationError as exc: print(f"Configuration error: {exc}", ...)` at lines 105-109 |
| `src/mailroom/cli.py` | setup command without --ui-guide option | VERIFIED | No ui_guide mention anywhere in file |
| `src/mailroom/setup/provisioner.py` | run_setup() without ui_guide parameter | VERIFIED | No ui_guide mention anywhere in file |
| `src/mailroom/setup/sieve_guidance.py` | generate_sieve_guidance(settings) only, no _build_ui_guide, no commented sieve blocks | VERIFIED | Signature confirmed at line 19; no _build_ui_guide; no fileinto/jmapquery commented blocks |
| `tests/test_config.py` | Case-insensitive rejection tests | VERIFIED | test_lowercase_inbox_rejected, test_uppercase_inbox_rejected, test_derived_lowercase_inbox_rejected all present and passing |
| `tests/test_sieve_guidance.py` | TestGenerateGuidanceUIGuideMode and test_sieve_reference_snippets removed; call signatures updated | VERIFIED | No such class or test found; all remaining calls use `generate_sieve_guidance(settings)` |
| `human-tests/test_14_setup_dry_run.py` | run_setup call without ui_guide | VERIFIED | No ui_guide in file |
| `human-tests/test_15_setup_apply.py` | run_setup calls without ui_guide | VERIFIED | No ui_guide in file |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/mailroom/core/config.py` | `tests/test_config.py` | case-insensitive CFG-02 tests | VERIFIED | 6 tests in TestDestinationMailboxInboxRejected including inbox/INBOX/derived variants; all pass |
| `src/mailroom/setup/sieve_guidance.py` | `src/mailroom/setup/provisioner.py` | generate_sieve_guidance(settings) call signature | VERIFIED | No ui_guide parameter on either side; signature matches |
| `src/mailroom/workflows/screener.py` | `src/mailroom/core/config.py` | get_parent_chain import and usage | VERIFIED | Import at screener.py:10; used at lines 330 and 371 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CFG-01 | 11-01, 11-02 | add_to_inbox per category, no inheritance through parent chain | SATISFIED | add_to_inbox on TriageCategory/ResolvedCategory; only checked on triaged category in screener (line 375) |
| CFG-02 | 11-01, 11-04 | System rejects destination_mailbox: Inbox with clear error — case-insensitive | SATISFIED | `resolved_mailbox.lower() == "inbox"` at config.py:193; 6 rejection tests pass; clean ValidationError output in __main__.py |
| CFG-03 | 11-01 | Child categories resolve as fully independent (own label, group, mailbox) | SATISFIED | Single-pass resolve_categories; TestChildIndependence passes |
| CFG-04 | 11-02 | Parent relationship applies parent's label chain on triage (additive) | SATISFIED | Additive mailbox filing and group assignment in screener |
| CFG-05 | 11-01 | Circular parent references detected and rejected | SATISFIED | Check #4 in _validate_categories; TestValidationCircularParents passes |
| CFG-06 | 11-01 | No backward compatibility — current format only | SATISFIED | No migration shims, legacy fallbacks, or version detection in config.py |
| CFG-07 | 11-03 | Setup CLI provisions independent mailbox/contact group per child category | SATISFIED | required_mailboxes and contact_groups iterate all resolved_categories |
| CFG-08 | 11-03, 11-04 | Sieve guidance reflects additive parent label semantics; clean output | SATISFIED | All 7 categories shown; grouped by parent; no dead ui_guide code; no commented sieve blocks; 24 sieve tests pass |

**Orphaned requirements:** None. CFG-01 through CFG-08 are all claimed by Phase 11 plans and all verified.

### Anti-Patterns Found

None. Scanned all modified files for TODO/FIXME/HACK/placeholder markers, empty returns, and stub implementations. Clean.

### Human Verification Required

#### 1. Sieve Guidance Visual Rendering

**Test:** Run `mailroom setup` against a live config with default categories and inspect the sieve guidance section
**Expected:** BOLD category names, CYAN mailbox names, MAGENTA keywords visible in terminal; children indented after parent; IMPORTANT note prominent at top; no commented sieve blocks visible
**Why human:** ANSI rendering and visual layout cannot be verified programmatically without a real TTY session

#### 2. Setup CLI Provisioning of Child Category Resources

**Test:** Run `mailroom setup` (or `mailroom setup --plan`) against a fresh Fastmail account with default config
**Expected:** Separate mailboxes and contact groups provisioned for Person, Billboard, Truck in addition to root categories
**Why human:** provisioner.py integration with real Fastmail JMAP/CardDAV APIs cannot be verified from tests alone

#### 3. Clean ValidationError Output

**Test:** Set `destination_mailbox: inbox` (lowercase) in config and run `mailroom`
**Expected:** Single clean stderr message like "Configuration error: ..." with the helpful add_to_inbox hint; no raw Pydantic traceback
**Why human:** stderr output formatting verified by inspection, not by automated test on the __main__.py entry point

### Test Suite Results

| Test File | Count | Result |
|-----------|-------|--------|
| tests/test_config.py | 64 (+3 case-insensitive variants vs. initial) | PASSED |
| tests/test_screener_workflow.py | 103 | PASSED |
| tests/test_sieve_guidance.py | 24 (-14 deleted UI guide + sieve reference tests vs. initial) | PASSED |
| tests/test_colors.py | included | PASSED |
| **Full suite** | **313** | **PASSED** |

### Commit Verification

| Commit | Description | Plan |
|--------|-------------|------|
| `20abee2` | test(11-01): failing tests for config layer v1.2 | 11-01 RED |
| `00685b8` | feat(11-01): implement config layer v1.2 | 11-01 GREEN |
| `20c17fd` | test(11-02): failing tests for additive parent chain | 11-02 RED |
| `257f0ce` | feat(11-02): implement additive parent chain in screener workflow | 11-02 GREEN |
| `acb0001` | test(11-03): failing tests for all-category sieve guidance | 11-03 RED |
| `75765f5` | feat(11-03): rewrite sieve guidance with all-category display | 11-03 GREEN |
| `43c7019` | test(11-04): failing tests for case-insensitive CFG-02 rejection | 11-04 RED |
| `f7669c8` | feat(11-04): case-insensitive CFG-02 + clean ValidationError | 11-04 GREEN |
| `be7a3b4` | feat(11-04): remove --ui-guide flag and commented sieve blocks | 11-04 cleanup |

### Re-Verification Summary

Initial verification (2026-03-02) passed 16/16 truths. UAT conducted by the operator identified 2 minor gaps which have been closed by Plan 04.

**Gap 1 (CFG-02 case sensitivity) — CLOSED:** `config.py:193` comparison was `resolved_mailbox == "Inbox"` — case-sensitive. Lowercase "inbox" bypassed the helpful error and failed later with a confusing message. Fixed by changing to `resolved_mailbox.lower() == "inbox"`. Three new test methods added (test_lowercase_inbox_rejected, test_uppercase_inbox_rejected, test_derived_lowercase_inbox_rejected). All 6 CFG-02 rejection tests pass. ValidationError is now caught in `__main__.py` and printed as a clean one-line message.

**Gap 2 (Sieve guidance clutter) — CLOSED:** The `--ui-guide` CLI flag was an outdated code path and `_build_ui_guide()` (65 lines) was dead code. Commented sieve equivalent blocks (fileinto/jmapquery) in `_build_sieve_snippets` added noise. Removed from cli.py, provisioner.py, sieve_guidance.py, all tests, and human tests. 8 dead tests deleted, ~150 lines of dead code removed. The informational jmapquery mention retained as explanatory text (not a commented sieve block).

No regressions introduced. All 313 tests pass.

---

_Verified: 2026-03-03_
_Verifier: Claude (gsd-verifier)_
