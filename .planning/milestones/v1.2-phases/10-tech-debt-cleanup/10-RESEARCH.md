# Phase 10: Tech Debt Cleanup - Research

**Researched:** 2026-03-02
**Domain:** Internal codebase cleanup (Pydantic config, test hygiene, Docker test, process docs)
**Confidence:** HIGH

## Summary

Phase 10 addresses four concrete tech debt items from the v1.1 milestone audit plus a missing verification document. All five items are well-scoped, low-risk, and involve modifying existing files in known locations. No new libraries, no new architecture, no external dependencies.

The changes span three domains: (1) exposing a private Pydantic attribute as a public property and updating its one consumer, (2) fixing a Docker human test to pass config via volume mount instead of an ignored env var, (3) cleaning stale env var names from the test fixture, and (4) writing a retroactive VERIFICATION.md for Phase 09.1.1 based on its completed UAT results.

**Primary recommendation:** Implement all five items in a single plan with one task per DEBT requirement. Each task is independent, small (1-5 lines changed per file), and can be verified with existing tests.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEBT-01 | Phase 09.1.1 VERIFICATION.md written to close audit gap | UAT 8/8 results in `09.1.1-UAT.md`, two SUMMARY files (`09.1.1-01-SUMMARY.md`, `09.1.1-02-SUMMARY.md`), and audit report all provide content. Format from `09.1-VERIFICATION.md` serves as template. |
| DEBT-02 | `resolved_categories` exposed as public property on MailroomSettings | Private attribute `_resolved_categories` set via `object.__setattr__` in model_validator at line 369 of `config.py`. Four internal properties already consume it. Adding a `@property` is a one-line addition. |
| DEBT-03 | `sieve_guidance.py` uses public `resolved_categories` interface | Single access point at line 43: `settings._resolved_categories`. Also referenced in docstring at lines 29 and 35. Change to `settings.resolved_categories` after DEBT-02 is done. |
| DEBT-04 | `test_13_docker_polling.py` passes poll interval via config.yaml mount | Line 95 sets `MAILROOM_POLL_INTERVAL=30` env var, which is silently ignored post-config.yaml migration. Must create a temp config.yaml with `polling.interval: 30` and mount it via `docker run -v`. |
| DEBT-05 | Stale env var names removed from `conftest.py` cleanup list | Lines 24-31 list 8 env vars that no longer map to any `MailroomSettings` field. Only 3 vars (JMAP_TOKEN, CARDDAV_USERNAME, CARDDAV_PASSWORD) are still valid as flat env vars. |
</phase_requirements>

## Standard Stack

No new libraries needed. This phase works entirely with existing project dependencies.

### Core
| Library | Version | Purpose | Why Relevant |
|---------|---------|---------|--------------|
| pydantic | existing | BaseModel and property decorators for MailroomSettings | DEBT-02 adds a `@property` to the existing Pydantic model |
| pydantic-settings | existing | BaseSettings with YAML source | Understanding which env vars map to fields (DEBT-04, DEBT-05) |
| pytest | existing | Unit test framework | DEBT-05 modifies conftest.py fixture |
| Docker | existing | Container runtime | DEBT-04 modifies Docker human test |

### Alternatives Considered

None -- all changes use existing stack.

## Architecture Patterns

### Pattern 1: Adding a Public Property to Pydantic BaseSettings

**What:** Expose `_resolved_categories` as a `@property` named `resolved_categories` on `MailroomSettings`, following the same pattern already used by `triage_labels`, `label_to_category_mapping`, `required_mailboxes`, and `contact_groups`.

**When to use:** When internal computed state needs external access.

**Current code (config.py line 365-403):**
```python
@model_validator(mode="after")
def resolve_and_validate_categories(self) -> Self:
    resolved = resolve_categories(self.triage.categories)
    object.__setattr__(self, "_resolved_categories", resolved)
    object.__setattr__(
        self, "_label_to_category", {r.label: r for r in resolved}
    )
    return self

@property
def triage_labels(self) -> list[str]:
    return [c.label for c in self._resolved_categories]
```

**New property to add:**
```python
@property
def resolved_categories(self) -> list[ResolvedCategory]:
    """Return all resolved triage categories."""
    return list(self._resolved_categories)
```

**Key decision: Return a copy (`list(...)`) not the internal list.** This prevents external code from mutating the internal state. All existing properties already follow this pattern (e.g., `triage_labels` creates a new list, `label_to_category_mapping` returns `dict(...)`, `contact_groups` returns `sorted(set(...))`.

### Pattern 2: Docker Volume Mount for Config File in Human Test

**What:** Create a temporary `config.yaml` file with the desired poll interval, then mount it into the container using `docker run -v`.

**Current code (test_13 line 95):**
```python
env_flags.extend(["-e", "MAILROOM_POLL_INTERVAL=30"])
```

**Why this fails:** Post Phase 9.1, `MailroomSettings` reads polling interval from `config.yaml` only. There is no `env_nested_delimiter` set, so `MAILROOM_POLL_INTERVAL` does not map to `polling.interval`. The env var is silently ignored and the container uses the default 60-second interval.

**How the Helm chart solves this (for reference):** The Deployment template mounts a ConfigMap as `/app/config.yaml` and sets `MAILROOM_CONFIG=/app/config.yaml`. The human test should follow the same pattern: write a config.yaml file, mount it at `/app/config.yaml`, and set the `MAILROOM_CONFIG` env var.

**Approach:**
```python
import tempfile

# Write config.yaml with desired poll interval
config_content = """\
polling:
  interval: 30
"""
config_file = Path(tempfile.mkdtemp()) / "config.yaml"
config_file.write_text(config_content)

# Mount into container
docker_run_args = [
    "run", "-d",
    "--name", CONTAINER_NAME,
    "-p", "8080:8080",
    "-v", f"{config_file}:/app/config.yaml:ro",
    "-e", "MAILROOM_CONFIG=/app/config.yaml",
    *env_flags,
    IMAGE_TAG,
]
```

**Note:** The Dockerfile's runtime stage has `USER 9999` (non-root) but the volume mount with `:ro` is readable. The `MAILROOM_CONFIG` env var tells MailroomSettings where to find the config file.

### Pattern 3: conftest.py Env Var Cleanup

**What:** The autouse `_set_config_path` fixture removes host env vars that could leak into tests. After the config.yaml migration, most `MAILROOM_*` env vars are no longer recognized by pydantic-settings.

**Current env vars in cleanup list (lines 20-31):**
| Env Var | Status | Reason |
|---------|--------|--------|
| `MAILROOM_JMAP_TOKEN` | KEEP | Direct flat field on MailroomSettings |
| `MAILROOM_CARDDAV_USERNAME` | KEEP | Direct flat field on MailroomSettings |
| `MAILROOM_CARDDAV_PASSWORD` | KEEP | Direct flat field on MailroomSettings |
| `MAILROOM_POLL_INTERVAL` | REMOVE | Was flat field, now `polling.interval` in YAML only |
| `MAILROOM_LOG_LEVEL` | REMOVE | Was flat field, now `logging.level` in YAML only |
| `MAILROOM_SCREENER_MAILBOX` | REMOVE | Was flat field, now `triage.screener_mailbox` in YAML only |
| `MAILROOM_TRIAGE_CATEGORIES` | REMOVE | Was flat field, now `triage.categories` in YAML only |
| `MAILROOM_DEBOUNCE_SECONDS` | REMOVE | Was flat field, now `polling.debounce_seconds` in YAML only |
| `MAILROOM_LABEL_MAILROOM_ERROR` | REMOVE | Was flat field, now `labels.mailroom_error` in YAML only |
| `MAILROOM_LABEL_MAILROOM_WARNING` | REMOVE | Was flat field, now `labels.mailroom_warning` in YAML only |
| `MAILROOM_WARNINGS_ENABLED` | REMOVE | Was flat field, now `labels.warnings_enabled` in YAML only |

**Why they are truly stale:** `MailroomSettings` has `env_prefix="MAILROOM_"` but no `env_nested_delimiter`. Without a delimiter, pydantic-settings cannot map flat env vars like `MAILROOM_POLL_INTERVAL` to nested fields like `polling.interval`. Only top-level fields (`jmap_token`, `carddav_username`, `carddav_password`) are reachable via env vars.

**Result:** Remove the 8 stale vars (lines 24-31). Keep only the 3 valid auth vars.

**Note:** The audit report says "7 vars" but the actual count is 8. The discrepancy is in the original audit -- the code has 8 stale entries.

### Pattern 4: Writing VERIFICATION.md from UAT Results

**What:** Write a VERIFICATION.md for Phase 09.1.1 based on the completed UAT results (8/8 passed) and the two SUMMARY files.

**Location:** `.planning/milestones/v1.1-phases/09.1.1-helm-chart-migration-with-podsecurity-hardening/09.1.1-VERIFICATION.md`

**Source material available:**
- `09.1.1-UAT.md` -- 8 test scenarios, all passed
- `09.1.1-01-SUMMARY.md` -- Plan 01 accomplishments and commits
- `09.1.1-02-SUMMARY.md` -- Plan 02 accomplishments and commits
- `09.1.1-CONTEXT.md` -- Phase context and decisions
- `09.1-VERIFICATION.md` -- Template/format reference from parent phase

**Key facts for verification content:**
- No formal requirement IDs (inserted phase, not mapped in REQUIREMENTS.md)
- 5 success criteria from phase planning (Helm lint, resource rendering, PSS restricted, Setup Job hook, ConfigMap config.yaml)
- UAT covered 8 scenarios covering all success criteria plus additional validations
- 2 plan executions, 4 total task commits

### Anti-Patterns to Avoid

- **Changing internal callers of `_resolved_categories`:** Only `sieve_guidance.py` is an external consumer. The four existing properties on `MailroomSettings` itself (`triage_labels`, `label_to_category_mapping`, `required_mailboxes`, `contact_groups`) should continue using `self._resolved_categories` directly -- they are internal to the class and don't need the property indirection.
- **Adding `env_nested_delimiter` to fix the poll interval env var:** This would be a config system change with broad implications. The correct fix is volume mounting a config.yaml, matching the production Helm pattern.
- **Removing the MAILROOM_LOG_LEVEL env var from test_13:** The human test also sets `MAILROOM_LOG_LEVEL=debug` on line 97. This has the same problem as POLL_INTERVAL -- it is silently ignored. Should be added to the mounted config.yaml as `logging.level: debug`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Config.yaml for Docker test | Inline string in docker command | Write a temp file and volume mount | Docker requires an actual file path for -v mounts |
| VERIFICATION.md content | Regenerate from scratch | UAT results + SUMMARY files | All evidence already exists in planning docs |

## Common Pitfalls

### Pitfall 1: Forgetting MAILROOM_LOG_LEVEL in test_13

**What goes wrong:** Fixing `MAILROOM_POLL_INTERVAL` but leaving `MAILROOM_LOG_LEVEL=debug` as an env var. The log level override is also silently ignored.
**Why it happens:** The audit only called out line 95 (POLL_INTERVAL). Line 97 has the same problem.
**How to avoid:** Include `logging.level: debug` in the mounted config.yaml file.
**Warning signs:** Container logs show `info` level instead of `debug` level.

### Pitfall 2: Returning the Internal List Directly from resolved_categories Property

**What goes wrong:** External code could accidentally mutate the internal `_resolved_categories` list.
**Why it happens:** Python properties that return `self._list` return a reference, not a copy.
**How to avoid:** Return `list(self._resolved_categories)` (a copy), consistent with how `label_to_category_mapping` returns `dict(self._label_to_category)`.
**Warning signs:** Mysterious test failures if any code appends to or modifies the returned list.

### Pitfall 3: Not Updating sieve_guidance.py Docstring

**What goes wrong:** Code references `_resolved_categories` in docstring even after switching to public property.
**Why it happens:** Docstrings at lines 29 and 35 explicitly mention `settings._resolved_categories`.
**How to avoid:** Update all three references: line 29 (function docstring), line 35 (Args docstring), and line 43 (actual access).
**Warning signs:** Stale documentation referencing private API.

### Pitfall 4: Counting Stale Env Vars as 7 (Audit Says 7, Reality is 8)

**What goes wrong:** Only removing 7 of the 8 stale vars because the audit said 7.
**Why it happens:** The v1.1 audit report counted "7 vars" but there are actually 8 stale entries in lines 24-31 of conftest.py.
**How to avoid:** Count the actual lines in conftest.py. Remove all 8: POLL_INTERVAL, LOG_LEVEL, SCREENER_MAILBOX, TRIAGE_CATEGORIES, DEBOUNCE_SECONDS, LABEL_MAILROOM_ERROR, LABEL_MAILROOM_WARNING, WARNINGS_ENABLED.
**Warning signs:** One leftover stale env var that serves no purpose.

## Code Examples

### DEBT-02: Add resolved_categories Property

```python
# In src/mailroom/core/config.py, after the existing contact_groups property (line 403)
@property
def resolved_categories(self) -> list[ResolvedCategory]:
    """Return all resolved triage categories."""
    return list(self._resolved_categories)
```

### DEBT-03: Update sieve_guidance.py

```python
# Line 43: Change from private to public access
root_categories = [
    cat for cat in settings.resolved_categories if cat.parent is None
]
```

```python
# Line 29: Update docstring
"""Generate sieve rule guidance for all configured root categories.

Iterates over settings.resolved_categories, skipping child categories
...
"""
```

### DEBT-04: Volume Mount Config in test_13

```python
# Replace line 95 (MAILROOM_POLL_INTERVAL env var) with config.yaml mount
import tempfile

# Write config.yaml with poll interval and log level overrides
config_content = """\
polling:
  interval: 30
logging:
  level: debug
"""
config_dir = Path(tempfile.mkdtemp())
config_file = config_dir / "config.yaml"
config_file.write_text(config_content)

# In docker run command, add volume mount and MAILROOM_CONFIG env var:
# -v {config_file}:/app/config.yaml:ro
# -e MAILROOM_CONFIG=/app/config.yaml
```

Also remove the stale env var lines:
```python
# DELETE these lines (95-98):
# env_flags.extend(["-e", "MAILROOM_POLL_INTERVAL=30"])
# env_flags.extend(["-e", "MAILROOM_LOG_LEVEL=debug"])
```

### DEBT-05: Clean conftest.py

```python
# Replace lines 20-31 with only valid env vars
for var in [
    "MAILROOM_JMAP_TOKEN",
    "MAILROOM_CARDDAV_USERNAME",
    "MAILROOM_CARDDAV_PASSWORD",
]:
    monkeypatch.delenv(var, raising=False)
```

## Open Questions

1. **Should the new `resolved_categories` property also be tested directly?**
   - What we know: The property is consumed by `sieve_guidance.py` and exercised transitively through `triage_labels`, `contact_groups`, etc.
   - What's unclear: Whether a dedicated test for `resolved_categories` is warranted.
   - Recommendation: Add one simple test that verifies `settings.resolved_categories` returns a list of `ResolvedCategory` objects with the expected length. This is minimal effort and documents the new public interface.

2. **Should existing internal `self._resolved_categories` references in config.py be changed to `self.resolved_categories`?**
   - What we know: Four properties (`triage_labels`, `label_to_category_mapping`, `required_mailboxes`, `contact_groups`) use `self._resolved_categories` internally.
   - What's unclear: Whether internal consistency matters more than the slight overhead of property call vs. direct attribute access.
   - Recommendation: Keep internal properties using `self._resolved_categories`. They are inside the class and don't benefit from the abstraction. This matches common Python practice (classes access their own private attributes directly).

## Sources

### Primary (HIGH confidence)
- **`src/mailroom/core/config.py`** -- Full MailroomSettings implementation, model_validator, properties, env_prefix config
- **`src/mailroom/setup/sieve_guidance.py`** -- The single external consumer of `_resolved_categories`
- **`tests/conftest.py`** -- Autouse fixture with env var cleanup list
- **`human-tests/test_13_docker_polling.py`** -- Docker polling test with stale env var
- **`helm/mailroom/templates/deployment.yaml`** -- Reference implementation for config.yaml volume mounting
- **`.planning/milestones/v1.1-MILESTONE-AUDIT.md`** -- Source of all 4 tech debt items
- **`09.1.1-UAT.md`, `09.1.1-01-SUMMARY.md`, `09.1.1-02-SUMMARY.md`** -- Source material for VERIFICATION.md
- **`09.1-VERIFICATION.md`** -- Format template for VERIFICATION.md

### Secondary (MEDIUM confidence)
- None needed -- all findings based on direct code inspection.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing code
- Architecture: HIGH -- all patterns are single-file edits following existing conventions
- Pitfalls: HIGH -- identified from direct code reading, not speculation

**Research date:** 2026-03-02
**Valid until:** Indefinite (internal codebase cleanup, no external dependency drift)
