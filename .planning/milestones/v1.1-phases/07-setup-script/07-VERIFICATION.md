---
phase: 07-setup-script
verified: 2026-02-27T12:30:00Z
status: passed
score: 23/23 must-haves verified
re_verification:
  previous_status: passed
  previous_score: 18/18
  gaps_closed:
    - "Sieve rules section appears BEFORE resource plan (output reordered)"
    - "Exists vs create statuses are visually distinct via ANSI color"
    - "Resources split into 4 categories: Mailboxes, Action Labels, Contact Groups, Mailroom"
    - "@MailroomError and @MailroomWarning appear in a separate Mailroom section"
    - "UI guide mode highlights override names (e.g., Inbox from Imbox) in cyan"
  gaps_remaining: []
  regressions: []
---

# Phase 7: Setup Script Verification Report

**Phase Goal:** Users can run a single command to provision all required Fastmail resources for their configured categories, with clear guidance for the one manual step (sieve rules)
**Verified:** 2026-02-27
**Status:** passed
**Re-verification:** Yes — after Plan 04 gap closure (output visual hierarchy + override highlighting)

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                     | Status   | Evidence |
|----|-------------------------------------------------------------------------------------------|----------|----------|
| 1  | JMAPClient can create a mailbox with name and optional parentId                           | VERIFIED | `create_mailbox()` at jmap.py:154, Mailbox/set JMAP call |
| 2  | JMAPClient exposes session capabilities for downstream sieve checking                     | VERIFIED | `session_capabilities` property at jmap.py:41 |
| 3  | CardDAVClient can create an Apple-style contact group vCard                               | VERIFIED | `create_group()` at carddav.py:285, X-ADDRESSBOOKSERVER-KIND:group |
| 4  | CLI framework dispatches `setup` and `run` subcommands                                    | VERIFIED | `cli.py` Click group, both subcommands present |
| 5  | `python -m mailroom` (no subcommand) still runs the service                               | VERIFIED | `invoke_without_command=True` in cli.py:12 |
| 6  | Dry-run shows what would be created without changing Fastmail                             | VERIFIED | `run_setup(apply=False)` calls `plan_resources` + `print_plan`, no writes |
| 7  | `--apply` creates missing mailboxes and contact groups on Fastmail                        | VERIFIED | `apply_resources()` calls `jmap.create_mailbox` and `carddav.create_group` |
| 8  | Second run of `--apply` reports all items as "exists" with no duplicates                  | VERIFIED | `plan_resources` checks existing state; human-tests/test_15 confirms live idempotency |
| 9  | Failed resource creation is reported inline with error reason                             | VERIFIED | `apply_resources` catches RuntimeError/HTTPStatusError; `_format_status` renders "FAILED: ..." |
| 10 | Parent mailbox failure causes child mailboxes to be skipped                               | VERIFIED | `failed_names` set tracked; children get status="skipped" + error="parent failed" |
| 11 | Pre-flight check validates JMAP and CardDAV connectivity before provisioning              | VERIFIED | `run_setup` connects both clients first with specific error messages, returns 1 on failure |
| 12 | Exit code 0 when all good, 1 when any failure                                             | VERIFIED | `run_setup` returns 1 if `has_failures`, 0 otherwise; CLI calls `sys.exit(exit_code)` |
| 13 | Setup output includes sieve rule guidance for ALL configured categories                   | VERIFIED | `generate_sieve_guidance` called in `run_setup` in both dry-run and apply paths |
| 14 | Default output shows copy-paste sieve-style snippets for every category                   | VERIFIED | `_build_sieve_snippets` iterates root categories with fileinto/jmapquery reference |
| 15 | `--ui-guide` flag shows Fastmail Settings UI step-by-step instructions instead            | VERIFIED | `_build_ui_guide` in sieve_guidance.py:114, no sieve code, Settings > Filters & Rules steps |
| 16 | Screener catch-all rule guidance is always included                                       | VERIFIED | Both `_build_sieve_snippets` and `_build_ui_guide` append screener section unconditionally |
| 17 | Human test verifies dry-run output format against real Fastmail                           | VERIFIED | `human-tests/test_14_setup_dry_run.py` 6 steps; UAT 9/9 passed 2026-02-27 |
| 18 | Human test verifies apply creates resources and idempotent re-run                         | VERIFIED | `human-tests/test_15_setup_apply.py` 6 steps; UAT 9/9 passed 2026-02-27 |
| 19 | Sieve rules section appears BEFORE resource plan in output                                | VERIFIED | provisioner.py:252 guidance printed before plan at line 254 (dry-run); same at lines 259/261 (apply) |
| 20 | Exists vs create statuses are visually distinct via ANSI color                            | VERIFIED | reporting.py:22-60: green exists/created, yellow create, red failed, dim skipped; NO_COLOR + TTY-aware |
| 21 | Resources split into 4 categories: Mailboxes, Action Labels, Contact Groups, Mailroom     | VERIFIED | reporting.py:106-115: 4-way split; test_dry_run_output asserts all 4 section headers present |
| 22 | @MailroomError and @MailroomWarning appear in separate Mailroom section, not Mailboxes    | VERIFIED | provisioner.py:58-90: `mailroom_names` set, kind="mailroom"; test_categorizes_correctly asserts exclusion from mailboxes |
| 23 | UI guide mode highlights override names (e.g., Inbox from Imbox) in cyan                 | VERIFIED | sieve_guidance.py:37-41: `_highlight_folder()` compares `destination_mailbox != name`, wraps with `_CYAN`; test_override_name_colored_when_tty passes |

**Score:** 23/23 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/mailroom/cli.py` | Click CLI group with setup and run subcommands | VERIFIED | `invoke_without_command=True`, `--apply` and `--ui-guide` flags |
| `src/mailroom/__main__.py` | Dispatches through CLI, preserves main() | VERIFIED | `from mailroom.cli import cli; cli()` in `__main__` block; `main()` unchanged |
| `src/mailroom/clients/jmap.py` | `create_mailbox` method and `session_capabilities` property | VERIFIED | `create_mailbox()` at line 154, `session_capabilities` property at line 41 |
| `src/mailroom/clients/carddav.py` | `create_group` and `list_groups` methods | VERIFIED | `list_groups()` at line 187, `create_group()` at line 285 |
| `src/mailroom/setup/__init__.py` | Empty package init | VERIFIED | File exists |
| `src/mailroom/setup/provisioner.py` | `plan_resources`, `apply_resources`, `run_setup`; sieve before plan; mailroom kind | VERIFIED | 266 lines, guidance at line 252 before `print_plan` at 254; mailroom_names at lines 58-90 |
| `src/mailroom/setup/reporting.py` | ANSI-colored terraform-style output with 4 resource categories | VERIFIED | 135 lines, ANSI constants, `_use_color()`, `_color()`, 4-section `print_plan` |
| `src/mailroom/setup/sieve_guidance.py` | Color-coded override folder names in both modes | VERIFIED | 152 lines, `_highlight_folder()` at line 37, applied in both `_build_sieve_snippets` and `_build_ui_guide` |
| `tests/test_provisioner.py` | 11 tests covering plan/apply/reporting including mailroom kind and no-color | VERIFIED | 332 lines, 11 tests all passing; `test_categorizes_correctly` asserts kind="mailroom"; `test_no_color_when_not_tty` added |
| `tests/test_sieve_guidance.py` | 23 tests covering default, UI guide, custom, and override highlighting | VERIFIED | 238 lines, 23 tests all passing; `TestOverrideHighlighting` class with 7 tests |
| `human-tests/test_14_setup_dry_run.py` | Live Fastmail dry-run verification | VERIFIED | 6 steps; UAT confirmed passed |
| `human-tests/test_15_setup_apply.py` | Live Fastmail apply + idempotency verification | VERIFIED | 6 steps; UAT confirmed passed |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `src/mailroom/__main__.py` | `src/mailroom/cli.py` | `from mailroom.cli import cli` | WIRED | `from mailroom.cli import cli; cli()` in `__main__` block |
| `src/mailroom/cli.py` | `src/mailroom/__main__.py` | `from mailroom.__main__ import main` | WIRED | Line 23: import inside `run` command |
| `src/mailroom/cli.py` | `src/mailroom/setup/provisioner.py` | setup command calls `run_setup()` | WIRED | `from mailroom.setup.provisioner import run_setup` |
| `provisioner.py` | `sieve_guidance.py` | `generate_sieve_guidance` called BEFORE `print_plan` | WIRED | Line 252: guidance first; line 254: plan second (dry-run). Lines 259/261: same for apply. |
| `provisioner.py` | `jmap.py` | `create_mailbox` calls in `apply_resources` | WIRED | Line 143: `jmap.create_mailbox(action.name)` for mailboxes/labels/mailroom kinds |
| `provisioner.py` | `carddav.py` | `create_group` calls in `apply_resources` | WIRED | Line 170: `carddav.create_group(action.name)` for contact_group kind |
| `provisioner.py` | `config.py` | reads `required_mailboxes`, `contact_groups`, `triage_labels` | WIRED | Lines 55-90: all three properties accessed |
| `reporting.py` | `sys.stdout` | ANSI color codes for status differentiation | WIRED | `_GREEN`/`_YELLOW`/`_RED`/`_DIM`/`_CYAN` at lines 22-27; TTY-gated via `_use_color()` |
| `sieve_guidance.py` | `ResolvedCategory.destination_mailbox` | `_highlight_folder()` override detection | WIRED | Line 39: `if cat.destination_mailbox != cat.name`; called at lines 88 and 132 |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| SETUP-01 | 07-01, 07-02, 07-04 | Setup creates missing triage label mailboxes via JMAP Mailbox/set | SATISFIED | `create_mailbox()` in jmap.py; `apply_resources` processes mailbox/label/mailroom kinds via JMAP |
| SETUP-02 | 07-01, 07-02, 07-04 | Setup creates missing contact groups via CardDAV | SATISFIED | `create_group()` in carddav.py; `apply_resources` processes contact_group kind via CardDAV |
| SETUP-03 | 07-02, 07-03, 07-04 | Setup is idempotent — reports "already exists" for existing items | SATISFIED | `plan_resources` checks existing state; status="exists" not re-created; UAT test_15 confirmed |
| SETUP-04 | 07-03, 07-04 | Setup outputs human-readable sieve rule instructions | SATISFIED | `generate_sieve_guidance()` produces instructions for all root categories in both modes; now printed BEFORE resource plan |
| SETUP-05 | 07-02, 07-03, 07-04 | Setup requires `--apply` flag to make changes (dry-run by default) | SATISFIED | `run_setup(apply=False)` only plans and prints, no writes; `--apply` flag required |
| SETUP-06 | 07-01, 07-02, 07-04 | Setup reads categories from same config as main service | SATISFIED | `run_setup` uses `MailroomSettings()` — same config class as `__main__.py` |

All 6 requirements satisfied. No orphaned requirements.

### Anti-Patterns Found

None. Scan of all Plan 04 modified files found:

- No TODO/FIXME/HACK/PLACEHOLDER comments in production code
- No empty implementations
- ANSI color helpers duplicated in reporting.py and sieve_guidance.py — documented design decision (6 lines each, different output patterns)
- No regressions in any prior functionality

### Human Verification Required

Two human integration tests exist and confirmed passing in UAT (2026-02-27, 9/9 passed). The Plan 04 output format changes (reordering + color) are verified by these same tests. No new human tests are required.

#### 1. Dry-run verification (test_14)

**Test:** `python human-tests/test_14_setup_dry_run.py`
**Expected:** 6 steps all PASS — sieve guidance appears first, then resource plan, no resources created, exit code 0
**Why human:** Requires real Fastmail credentials; verifies actual API connectivity and output ordering in a real terminal
**UAT result:** Passed (2026-02-27)

#### 2. Apply + idempotency verification (test_15)

**Test:** `python human-tests/test_15_setup_apply.py`
**Expected:** 6 steps all PASS — first apply creates missing resources, output has sieve guidance before plan, second apply shows all as "exists", both exit code 0
**Why human:** Requires real Fastmail; creates real resources; verifies idempotency against live state
**UAT result:** Passed (2026-02-27)

### Re-verification Summary

Plan 04 closed two UAT gaps identified after initial verification (score 18/18 -> 23/23):

**Gap 1 — Output visual hierarchy:** The previous output printed the resource plan before sieve guidance, making it hard to scan. Fixed by reordering `run_setup()` to call `generate_sieve_guidance` first in both dry-run and apply paths. Added ANSI color (green/yellow/red/dim) to status symbols and text via `_use_color()`/`_color()` helpers. Separated `@MailroomError`/`@MailroomWarning` into a dedicated 4th "Mailroom" resource section (kind="mailroom") removed from the Mailboxes section. The auto-fixed deviation in Plan 04 (adding mailroom kind handling to `apply_resources`) was correctly identified and implemented.

**Gap 2 — Override name highlighting:** `_highlight_folder()` in sieve_guidance.py compares `cat.destination_mailbox != cat.name` and wraps overrides with `_CYAN`. Applied in both `_build_sieve_snippets` and `_build_ui_guide`. Non-override names are printed without color. Color is disabled when NO_COLOR env var is set or stdout is not a TTY.

All 23 truths verified. 253 unit tests pass. Commits `0e4e644` and `e6ffa71` implement Plan 04. No regressions.

---

_Verified: 2026-02-27_
_Verifier: Claude (gsd-verifier)_
