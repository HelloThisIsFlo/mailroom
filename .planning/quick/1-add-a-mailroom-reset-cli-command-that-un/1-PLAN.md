---
phase: quick-1
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mailroom/cli.py
  - src/mailroom/clients/carddav.py
  - src/mailroom/clients/jmap.py
  - src/mailroom/reset/__init__.py
  - src/mailroom/reset/resetter.py
  - src/mailroom/reset/reporting.py
  - tests/test_resetter.py
autonomous: true
requirements: [RESET-01]

must_haves:
  truths:
    - "Running `python -m mailroom reset` shows a dry-run report of contacts to clean, emails to un-label, and group memberships to remove"
    - "Running `python -m mailroom reset --apply` executes all cleanup operations"
    - "Contacts with Mailroom notes have the note section stripped but are NOT deleted"
    - "All managed labels are removed from emails (triage labels, destination labels, error/warning labels) but Screener is untouched"
    - "All members are removed from managed contact groups but the groups themselves remain"
    - "Likely-created contacts are flagged separately in the report for manual deletion"
  artifacts:
    - path: "src/mailroom/reset/resetter.py"
      provides: "Reset planning and execution logic"
      exports: ["run_reset"]
    - path: "src/mailroom/reset/reporting.py"
      provides: "Reset report formatting"
      exports: ["print_reset_report"]
    - path: "src/mailroom/cli.py"
      provides: "CLI entry point with reset command"
      contains: "def reset"
    - path: "tests/test_resetter.py"
      provides: "Unit tests for reset logic"
      min_lines: 80
  key_links:
    - from: "src/mailroom/cli.py"
      to: "src/mailroom/reset/resetter.py"
      via: "cli reset command imports run_reset"
      pattern: "from mailroom\\.reset\\.resetter import run_reset"
    - from: "src/mailroom/reset/resetter.py"
      to: "src/mailroom/clients/jmap.py"
      via: "queries emails by label, batch removes labels"
      pattern: "jmap\\.(query_emails|batch_remove_labels)"
    - from: "src/mailroom/reset/resetter.py"
      to: "src/mailroom/clients/carddav.py"
      via: "lists all contacts, strips notes, removes from groups"
      pattern: "carddav\\.(list_all_contacts|remove_from_group)"
---

<objective>
Add a `reset` CLI command that undoes all mailroom changes: strips Mailroom notes from contacts, removes managed labels from all affected emails, and empties managed contact groups. Follows the existing setup command's dry-run/apply pattern.

Purpose: Enable clean-slate recovery -- user can reset and re-run setup + service without manual Fastmail cleanup.
Output: `src/mailroom/reset/` module with resetter + reporting, CLI wiring, and unit tests.
</objective>

<execution_context>
@/Users/flo/.claude/get-shit-done/workflows/execute-plan.md
@/Users/flo/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/mailroom/cli.py
@src/mailroom/setup/provisioner.py
@src/mailroom/setup/reporting.py
@src/mailroom/setup/colors.py
@src/mailroom/clients/carddav.py
@src/mailroom/clients/jmap.py
@src/mailroom/core/config.py
@tests/conftest.py
@tests/test_provisioner.py

<interfaces>
<!-- Key types and contracts the executor needs. Extracted from codebase. -->

From src/mailroom/clients/carddav.py:
```python
# Existing methods to use:
class CardDAVClient:
    def list_groups(self) -> dict[str, dict]:  # FN -> {href, etag, uid}
    def remove_from_group(self, group_name: str, contact_uid: str, max_retries: int = 3) -> str:
    def _parse_multistatus(self, xml_bytes: bytes) -> list[dict]:  # {href, etag, vcard_data}
    # Uses REPORT_ALL_VCARDS to fetch all vCards
    # _groups: dict[str, dict] — validated groups cache
    # _addressbook_url: str — base URL for addressbook

# New method needed: list_all_contacts() — fetch all non-group vCards
# New method needed: update_contact_note(href, etag, new_note_value) — PUT updated vCard
```

From src/mailroom/clients/jmap.py:
```python
class JMAPClient:
    def query_emails(self, mailbox_id: str, sender: str | None = None, limit: int = 100) -> list[str]:
    def resolve_mailboxes(self, required_names: list[str]) -> dict[str, str]:  # name -> id
    def batch_move_emails(self, email_ids: list[str], remove_mailbox_id: str, add_mailbox_ids: list[str]) -> None:
    # New method needed: batch_remove_labels(email_ids: list[str], mailbox_ids: list[str]) — remove multiple labels from emails in batches
```

From src/mailroom/core/config.py:
```python
class MailroomSettings:
    triage: TriageSettings  # .screener_mailbox, .categories
    labels: LabelSettings  # .mailroom_error, .mailroom_warning, .warnings_enabled
    resolved_categories: list[ResolvedCategory]  # .label, .contact_group, .destination_mailbox
    required_mailboxes: list[str]  # all mailbox names needed
    contact_groups: list[str]  # all group names
    triage_labels: list[str]  # all triage label names
```

From src/mailroom/setup/reporting.py:
```python
@dataclass
class ResourceAction:
    kind: str  # "mailbox", "label", "contact_group", "mailroom"
    name: str
    status: str  # "exists", "create", "created", "failed", "skipped"
```

Mailroom note header: "\u2014 Mailroom \u2014" (em-dash Mailroom em-dash)
Note format in contacts:
  "— Mailroom —\nTriaged to Feed on 2026-01-15"
  or with pre-existing note: "Old note\n\n— Mailroom —\nRe-triaged to Imbox on 2026-03-01"
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add client methods and build reset module with tests</name>
  <files>
    src/mailroom/clients/carddav.py,
    src/mailroom/clients/jmap.py,
    src/mailroom/reset/__init__.py,
    src/mailroom/reset/resetter.py,
    src/mailroom/reset/reporting.py,
    tests/test_resetter.py
  </files>
  <behavior>
    CardDAV client additions:
    - list_all_contacts() returns list of dicts with href, etag, uid, fn, emails (list[str]), note, group_memberships (list of group names from managed groups)
    - update_contact_vcard(href, etag, serialized_vcard) PUTs with If-Match

    JMAP client addition:
    - batch_remove_labels(email_ids, mailbox_ids_to_remove) removes multiple labels from emails in BATCH_SIZE chunks using Email/set patch syntax (mailboxIds/{id}: None for each label)

    Reset plan_reset():
    - Test: with 2 annotated contacts (one likely-created, one pre-existing with extra note) and emails in managed labels, plan returns correct counts
    - Test: Screener mailbox emails are NOT included in the label removal plan
    - Test: contacts with no Mailroom note section are excluded from cleaning plan
    - Test: likely-created detection: contact where (a) all group memberships are managed groups only, (b) note is ONLY the mailroom section (no pre-existing content), (c) gets flagged as likely_created=True

    Reset apply_reset():
    - Test: label removal calls batch_remove_labels for each managed label with correct email IDs
    - Test: group emptying calls remove_from_group for each member in each managed group
    - Test: note stripping removes "— Mailroom —" section but preserves pre-existing note text
    - Test: note that is ONLY mailroom section gets cleared to empty string
    - Test: operation order is (1) remove labels from emails, (2) remove contacts from groups, (3) strip notes from contacts

    Reporting:
    - Test: dry-run shows counts per section (emails, groups, contacts) with appropriate formatting
    - Test: likely-created contacts printed in separate section with distinct marker
  </behavior>
  <action>
    **1. Add CardDAV client methods** (`src/mailroom/clients/carddav.py`):

    Add `list_all_contacts()` method that uses `REPORT_ALL_VCARDS` (same as `list_groups`/`validate_groups`), but filters for NON-group vCards (items WITHOUT `x-addressbookserver-kind: group`). Returns list of dicts:
    ```python
    {
        "href": str,
        "etag": str,
        "uid": str,
        "fn": str,
        "emails": list[str],  # all EMAIL values lowercased
        "note": str,           # NOTE value or ""
        "vcard_data": str,     # raw vCard for re-serialization
    }
    ```

    Add `update_contact_vcard(href: str, etag: str, vcard_bytes: bytes) -> str` method that PUTs the serialized vCard to `https://{hostname}{href}` with `If-Match: {etag}` and `Content-Type: text/vcard; charset=utf-8`. Returns new etag.

    **2. Add JMAP client method** (`src/mailroom/clients/jmap.py`):

    Add `batch_remove_labels(email_ids: list[str], mailbox_ids: list[str]) -> None` method. Processes in `BATCH_SIZE` chunks. For each email, builds patch dict: `{f"mailboxIds/{mb_id}": None for mb_id in mailbox_ids}`. Uses `Email/set` with `update` dict. Raises RuntimeError if any notUpdated.

    **3. Create reset module** (`src/mailroom/reset/`):

    Create `__init__.py` (empty).

    Create `resetter.py` with these functions:

    `plan_reset(settings, jmap, carddav) -> ResetPlan` — builds a plan of what to clean:
    - Connect to JMAP, resolve all managed mailbox IDs (all from `settings.required_mailboxes` EXCEPT "Inbox" and `settings.triage.screener_mailbox`)
    - For each managed mailbox ID: query_emails to get email IDs (returns dict of mailbox_name -> list of email_ids)
    - Fetch all contacts via `carddav.list_all_contacts()`
    - Filter to contacts whose note contains the Mailroom header (`"\u2014 Mailroom \u2014"`)
    - For each annotated contact, check group memberships: iterate managed groups, fetch each group vCard, check if contact UID is a member
    - Determine `likely_created` flag for each contact: (a) every group membership is a managed group (no non-managed memberships), (b) note content is ONLY the mailroom section (strip the mailroom header and all lines after it -- if nothing remains, it's mailroom-only), (c) both conditions met
    - Return a `ResetPlan` dataclass containing:
      - `email_labels: dict[str, list[str]]` — mailbox_name -> email_ids
      - `group_members: dict[str, list[str]]` — group_name -> list of contact_uids
      - `contacts_to_clean: list[ContactCleanup]` — each with href, etag, fn, uid, note, stripped_note, likely_created, vcard_data
    - Use `@dataclass` for `ResetPlan` and `ContactCleanup`

    `apply_reset(plan: ResetPlan, jmap, carddav, settings) -> ResetResult`:
    - Step 1: For each managed label with emails, resolve mailbox ID and call `jmap.batch_remove_labels(email_ids, [mailbox_id])`
    - Step 2: For each managed group with members, call `carddav.remove_from_group(group_name, contact_uid)` for each member
    - Step 3: For each contact to clean, strip the Mailroom note section from the vCard. Parse note: if note contains `"\u2014 Mailroom \u2014"`, split on it, keep everything before it (stripped of trailing whitespace/newlines). If nothing before it, set note to empty. Re-serialize vCard with vobject and PUT via `carddav.update_contact_vcard()`.
    - Track counts and any errors
    - Return `ResetResult` dataclass with counts (emails_unlabeled, groups_emptied, contacts_cleaned, errors)

    `run_reset(apply: bool = False) -> int` — top-level entry point (same pattern as `run_setup`):
    - Load settings, connect JMAP + CardDAV
    - Call `plan_reset()` to build plan
    - Call `carddav.validate_groups(settings.contact_groups)` before planning (needed for group operations)
    - If not apply: print dry-run report, return 0
    - If apply: call `apply_reset()`, print result report, return 0 on success / 1 on errors

    **4. Create reporting** (`src/mailroom/reset/reporting.py`):

    `print_reset_report(plan_or_result, apply: bool)` — terraform-style output similar to setup reporting:
    - Use same color helpers from `mailroom.setup.colors`
    - Section "Email Labels to Clean": for each managed label with emails, show label name and count
    - Section "Contact Groups to Empty": for each group with members, show group name and member count
    - Section "Contacts to Clean": for each contact, show FN and "strip note" status
    - Section "Likely Mailroom-Created Contacts" (separate, only in output if any): list contacts flagged as likely_created with a note suggesting manual deletion
    - Summary line with total counts

    **5. Write tests** (`tests/test_resetter.py`):

    Follow existing test patterns from `tests/test_provisioner.py`. Use `unittest.mock.MagicMock` for JMAP/CardDAV clients. Use `mock_settings` fixture from conftest.

    Test classes:
    - `TestPlanReset`: plan correctly identifies annotated contacts, managed label emails, group memberships, likely-created flag, excludes Screener/Inbox
    - `TestApplyReset`: correct operation order, label removal calls, group emptying calls, note stripping logic (mailroom-only note -> empty, mixed note -> pre-existing preserved)
    - `TestResetReporting`: dry-run output format, apply output format, likely-created section

    For mocking `list_all_contacts`, return a list of contact dicts. For mocking `query_emails`, return email ID lists per mailbox. For mocking group membership, configure `remove_from_group` to track calls.
  </action>
  <verify>
    <automated>cd /Users/flo/Work/Private/Dev/Services/mailroom && python -m pytest tests/test_resetter.py -x -v</automated>
  </verify>
  <done>
    - CardDAV client has list_all_contacts() and update_contact_vcard() methods
    - JMAP client has batch_remove_labels() method
    - Reset module has plan_reset(), apply_reset(), run_reset() with dry-run/apply pattern
    - Reporting produces terraform-style output with separate likely-created section
    - All tests pass
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire CLI command and verify end-to-end</name>
  <files>src/mailroom/cli.py</files>
  <action>
    Add `reset` command to the Click CLI group in `src/mailroom/cli.py`, following the exact pattern of the existing `setup` command:

    ```python
    @cli.command()
    @click.option("--apply", is_flag=True, default=False, help="Apply changes (default is dry-run)")
    def reset(apply: bool) -> None:
        """Reset all Mailroom changes: clean contacts, un-label emails, empty groups."""
        from mailroom.reset.resetter import run_reset

        exit_code = run_reset(apply=apply)
        sys.exit(exit_code)
    ```

    Verify the CLI wiring works by running `python -m mailroom reset --help` and confirming the help text appears.
  </action>
  <verify>
    <automated>cd /Users/flo/Work/Private/Dev/Services/mailroom && python -m mailroom reset --help 2>&1 | grep -q "Reset all Mailroom changes" && echo "CLI wiring OK" && python -m pytest tests/ -x -q 2>&1 | tail -5</automated>
  </verify>
  <done>
    - `python -m mailroom reset --help` shows the reset command help
    - `python -m mailroom reset` would run dry-run mode (needs real credentials)
    - `python -m mailroom reset --apply` would execute cleanup (needs real credentials)
    - All existing tests still pass (no regressions)
  </done>
</task>

</tasks>

<verification>
1. `python -m pytest tests/test_resetter.py -x -v` -- all reset unit tests pass
2. `python -m pytest tests/ -x -q` -- full test suite passes (no regressions)
3. `python -m mailroom reset --help` -- shows help text for reset command
4. `python -m mailroom --help` -- shows reset alongside setup and run commands
</verification>

<success_criteria>
- `python -m mailroom reset` runs dry-run showing what would be cleaned (contacts, labels, groups)
- `python -m mailroom reset --apply` executes the cleanup operations
- Contacts are NOT deleted, only their Mailroom note section is stripped
- Screener mailbox is untouched
- Managed labels/groups remain but their contents are emptied
- Likely-created contacts are flagged separately in the report
- All unit tests pass
- No regressions in existing tests
</success_criteria>

<output>
After completion, create `.planning/quick/1-add-a-mailroom-reset-cli-command-that-un/1-SUMMARY.md`
</output>
