---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - .gitignore
  - human-tests/test_1_auth.py
  - human-tests/test_2_query.py
  - human-tests/test_3_label.py
  - pyproject.toml
  - uv.lock
autonomous: true
requirements: []
must_haves:
  truths:
    - "Phase 1 verification artifacts are committed to version control"
    - ".claude/ directory remains untracked and uncommitted"
    - "README.md remains uncommitted"
  artifacts:
    - path: ".gitignore"
      provides: "Ignore rules for .env, __pycache__, .venv, .ruff_cache, .pytest_cache"
    - path: "human-tests/test_1_auth.py"
      provides: "Manual verification test for JMAP auth + mailbox resolution"
    - path: "human-tests/test_2_query.py"
      provides: "Manual verification test for email query + sender extraction"
    - path: "human-tests/test_3_label.py"
      provides: "Manual verification test for label removal"
  key_links: []
---

<objective>
Commit the human verification tests, .gitignore, and dependency changes produced during Phase 1 verification.

Purpose: These files were created during phase verification but never committed. They belong in the repo as verification artifacts and project hygiene.
Output: Clean git commit with all Phase 1 verification artifacts tracked.
</objective>

<execution_context>
@/Users/flo/.claude/get-shit-done/workflows/execute-plan.md
@/Users/flo/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Stage and commit Phase 1 verification artifacts</name>
  <files>.gitignore, human-tests/test_1_auth.py, human-tests/test_2_query.py, human-tests/test_3_label.py, pyproject.toml, uv.lock</files>
  <action>
Stage the following files in a single commit:

1. `.gitignore` -- new file, ignores .env, __pycache__, .venv, .ruff_cache, .pytest_cache
2. `human-tests/test_1_auth.py` -- manual JMAP auth + mailbox resolution verification test
3. `human-tests/test_2_query.py` -- manual email query + sender extraction verification test
4. `human-tests/test_3_label.py` -- manual label removal verification test
5. `pyproject.toml` -- added python-dotenv>=1.2.1 to dev dependencies
6. `uv.lock` -- lock file updated with python-dotenv

Do NOT stage:
- `.claude/` -- local Claude Code config, not for repo
- `README.md` -- empty, user did not request it

Use commit message following repo convention:
```
chore(phase-01): add verification tests, gitignore, and dev dependency

Add human-tests/ for manual Phase 1 verification (auth, query, label).
Add .gitignore for standard Python/env ignores.
Add python-dotenv to dev dependencies for test env loading.
```
  </action>
  <verify>
    <automated>cd /Users/flo/Work/Private/Dev/Services/mailroom && git log -1 --oneline | grep -q "chore(phase-01)" && git diff --name-only HEAD~1 HEAD | sort</automated>
    <manual>Verify commit contains exactly 6 files: .gitignore, human-tests/test_1_auth.py, human-tests/test_2_query.py, human-tests/test_3_label.py, pyproject.toml, uv.lock</manual>
  </verify>
  <done>Single commit exists with all 6 verification artifacts. .claude/ and README.md remain untracked. Git working tree shows only .claude/ and README.md as untracked.</done>
</task>

</tasks>

<verification>
- `git log -1` shows the verification commit with conventional format
- `git status` shows only `.claude/` and `README.md` as untracked (not staged, not committed)
- `git show --stat HEAD` lists exactly 6 files
</verification>

<success_criteria>
All Phase 1 verification artifacts committed in a single clean commit following repo conventions. No unwanted files (.claude/, README.md) included.
</success_criteria>

<output>
After completion, create `.planning/quick/1-commit-human-tests-gitignore-and-depende/1-SUMMARY.md`
</output>
