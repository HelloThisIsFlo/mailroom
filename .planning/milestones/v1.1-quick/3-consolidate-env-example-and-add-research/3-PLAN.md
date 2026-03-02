---
phase: quick-3
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - human-tests/.env.example
  - human-tests/test_1_auth.py
  - human-tests/test_2_query.py
  - human-tests/test_3_label.py
  - human-tests/test_4_carddav_auth.py
  - human-tests/test_5_carddav_contacts.py
  - human-tests/test_6_carddav_groups.py
  - human-tests/test_7_screener_poll.py
  - human-tests/test_8_conflict_detection.py
  - human-tests/test_9_already_grouped.py
  - human-tests/test_10_retry_safety.py
  - human-tests/test_11_person_contact.py
  - human-tests/test_12_company_contact.py
  - human-tests/test_13_docker_polling.py
  - .env.example
  - .research/README.md
  - PROJECT_BRIEF.md
autonomous: true
requirements: []
must_haves:
  truths:
    - "All 13 human test scripts load .env from project root, not human-tests/"
    - "human-tests/.env.example no longer exists"
    - "Root .env.example header instructs users to cp .env.example .env (already true)"
    - ".research/ directory exists with README explaining its purpose"
    - "PROJECT_BRIEF.md moved to .research/project-brief.md"
  artifacts:
    - path: ".research/README.md"
      provides: "Explains purpose and conventions for .research/ directory"
    - path: ".research/project-brief.md"
      provides: "Historical project brief (moved from root)"
  key_links:
    - from: "human-tests/test_*.py"
      to: ".env (project root)"
      via: "load_dotenv with parent.parent path"
      pattern: "load_dotenv.*parent\\.parent"
---

<objective>
Consolidate environment configuration and create the .research directory.

Purpose: Eliminate the redundant human-tests/.env.example (root .env.example is canonical), point all 13 human test scripts at the root .env, and create .research/ as a home for freeform research artifacts.

Output: Cleaner repo with single .env.example, unified env loading, and a new .research/ directory with README and the moved PROJECT_BRIEF.md.
</objective>

<execution_context>
@/Users/flo/.claude/get-shit-done/workflows/execute-plan.md
@/Users/flo/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.env.example
@human-tests/.env.example
</context>

<tasks>

<task type="auto">
  <name>Task 1: Consolidate .env.example and update human test scripts</name>
  <files>
    human-tests/.env.example
    human-tests/test_1_auth.py
    human-tests/test_2_query.py
    human-tests/test_3_label.py
    human-tests/test_4_carddav_auth.py
    human-tests/test_5_carddav_contacts.py
    human-tests/test_6_carddav_groups.py
    human-tests/test_7_screener_poll.py
    human-tests/test_8_conflict_detection.py
    human-tests/test_9_already_grouped.py
    human-tests/test_10_retry_safety.py
    human-tests/test_11_person_contact.py
    human-tests/test_12_company_contact.py
    human-tests/test_13_docker_polling.py
    .env.example
  </files>
  <action>
    1. Delete `human-tests/.env.example` (git rm).

    2. In all 13 human test scripts, change the load_dotenv line from:
       `load_dotenv(Path(__file__).parent / ".env")`
       to:
       `load_dotenv(Path(__file__).resolve().parent.parent / ".env")`

       Use `.resolve()` to handle symlinks correctly. The `.parent.parent` navigates from `human-tests/` up to the project root.

       IMPORTANT: Only change the load_dotenv argument line. Do not modify anything else in these files.

    3. Add a comment to the root `.env.example` header noting it is the single source of truth for all scripts including human tests. Add one line after the existing header comment block (after line 3, before the blank line):
       `# This is the single source of truth -- human tests also load from root .env`

    Note: `.gitignore` already has both `.env` and `human-tests/.env` entries. The `human-tests/.env` gitignore entry is now vestigial but harmless -- leave it to avoid breaking anyone who already has a local `human-tests/.env`.
  </action>
  <verify>
    <automated>cd /Users/flo/Work/Private/Dev/Services/mailroom && python -c "
import pathlib
# Verify human-tests/.env.example is gone
assert not pathlib.Path('human-tests/.env.example').exists(), 'human-tests/.env.example still exists'

# Verify all 13 scripts use parent.parent
import re
for i in range(1, 14):
    matches = list(pathlib.Path('human-tests').glob(f'test_{i}_*.py'))
    assert len(matches) == 1, f'Missing test_{i}_*.py'
    content = matches[0].read_text()
    assert 'parent.parent' in content, f'{matches[0].name} missing parent.parent'
    assert 'Path(__file__).parent / \".env\"' not in content, f'{matches[0].name} still has old pattern'

# Verify root .env.example has the comment
env_example = pathlib.Path('.env.example').read_text()
assert 'single source of truth' in env_example, '.env.example missing consolidation comment'

print('All checks passed')
"</automated>
  </verify>
  <done>
    - human-tests/.env.example deleted
    - All 13 test scripts load .env from project root via parent.parent
    - Root .env.example annotated as single source of truth
  </done>
</task>

<task type="auto">
  <name>Task 2: Create .research directory and move PROJECT_BRIEF.md</name>
  <files>
    .research/README.md
    .research/project-brief.md
    PROJECT_BRIEF.md
  </files>
  <action>
    1. Create `.research/` directory.

    2. Create `.research/README.md` with content explaining:
       - Purpose: freeform space for research, discovery, and exploration artifacts that don't belong in `.planning/` (which is phase/milestone-oriented)
       - Organization: by theme, not by type (e.g., `.research/jmap-eventsource/` would contain both scripts and notes)
       - Committed to git (not ignored) so it travels with the repo
       - No strict conventions -- lightweight and free-form
       - Examples of what belongs here: discovery scripts, personal notes/findings, historical context, exploratory prototypes

    3. Move `PROJECT_BRIEF.md` to `.research/project-brief.md` using `git mv`. This is historical context that predates `.planning/` and is now fully captured there.
  </action>
  <verify>
    <automated>cd /Users/flo/Work/Private/Dev/Services/mailroom && python -c "
import pathlib
assert pathlib.Path('.research/README.md').exists(), '.research/README.md missing'
assert pathlib.Path('.research/project-brief.md').exists(), '.research/project-brief.md missing'
assert not pathlib.Path('PROJECT_BRIEF.md').exists(), 'PROJECT_BRIEF.md still at root'
readme = pathlib.Path('.research/README.md').read_text()
assert 'research' in readme.lower(), 'README missing research description'
print('All checks passed')
"</automated>
  </verify>
  <done>
    - .research/ directory exists with README.md
    - PROJECT_BRIEF.md moved to .research/project-brief.md
    - No PROJECT_BRIEF.md at root
  </done>
</task>

</tasks>

<verification>
1. `human-tests/.env.example` does not exist
2. All 13 `human-tests/test_*.py` scripts contain `parent.parent / ".env"` pattern
3. Root `.env.example` has "single source of truth" annotation
4. `.research/README.md` exists and describes the directory's purpose
5. `.research/project-brief.md` exists with original brief content
6. `PROJECT_BRIEF.md` no longer exists at project root
7. `git status` shows clean tracked changes (deletions + modifications + additions)
</verification>

<success_criteria>
- Running any human test with a root `.env` works (env vars load correctly)
- Single `.env.example` at root is the only example file in the repo
- `.research/` directory is committed and contains README + project brief
</success_criteria>

<output>
After completion, create `.planning/quick/3-consolidate-env-example-and-add-research/3-SUMMARY.md`
</output>
