# Phase 6: Configurable Categories - Research

**Researched:** 2026-02-26
**Domain:** Pydantic configuration modeling, JSON env var parsing, startup validation
**Confidence:** HIGH

## Summary

Phase 6 replaces the hardcoded triage category definitions in `MailroomSettings` with a single `MAILROOM_TRIAGE_CATEGORIES` JSON env var containing a list of category objects. The current codebase has 5 individual `label_to_*` fields, 4 `group_*` fields, and a hand-built `label_to_group_mapping` property that returns `dict[str, dict[str, str]]`. All of these collapse into one `list[TriageCategory]` field with derived defaults and a `@model_validator` that computes the label-to-category mapping.

Pydantic-settings natively parses JSON strings from environment variables for complex types (`list`, `dict`, sub-models) -- no custom parsing code is needed. A `list[TriageCategory]` field with a default factory produces the v1.0 defaults when the env var is absent, and parses the JSON array when present. The `@model_validator(mode='after')` pattern handles cross-field validation (duplicate names, parent references, circular chains) and can collect all errors before raising.

**Primary recommendation:** Define a `TriageCategory` Pydantic BaseModel with `name` (required) and optional override fields (`label`, `contact_group`, `destination_mailbox`, `contact_type`, `parent`). Use `@model_validator(mode='after')` on `MailroomSettings` to derive defaults, validate constraints, and build the resolved mapping. Remove all individual `label_to_*` and `group_*` fields.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Name-only config: user provides `{ "name": "Receipts" }` and label, group, mailbox are derived
- Derivation rules: label = `@To{NameNoSpaces}` (e.g., "Paper Trail" -> @ToPaperTrail), group = `{Name}`, mailbox = `{Name}`
- All derived fields are overridable: `label`, `contact_group`, `destination_mailbox` can each be explicitly set
- Category order in the JSON array has no semantic meaning -- no priority implied
- Person is a regular category with an optional `contact_type` field (default: "company")
- `contact_type` is restricted to known values: "company", "person" -- unknown values rejected at startup
- Optional `parent` field declares hierarchy: `{ "name": "Person", "parent": "Imbox", "contact_type": "person" }`
- Children inherit parent's `contact_group` and `destination_mailbox` (can be overridden)
- Shared contact groups are only allowed via parent relationship -- flagged otherwise
- Setup script (Phase 7) uses `parent` to create nested Fastmail mailboxes; engine doesn't use hierarchy
- No separate add-inbox flag -- `destination_mailbox` fully controls where emails land
- Imbox sets `destination_mailbox: "Inbox"` to deliver to Inbox; Feed sets `destination_mailbox: "Feed"` to stay out of Inbox
- Any valid Fastmail mailbox name allowed as destination -- not restricted to a known set
- Startup validates all destination mailboxes exist on Fastmail (crashes with clear error if missing)
- Full replacement: if `MAILROOM_TRIAGE_CATEGORIES` is set, it IS the complete category list -- no defaults mixed in
- No env var = built-in defaults matching v1.0 (Imbox, Person, Feed, Paper Trail, Jail)
- Fully custom allowed -- no default categories required, just at least one category
- Default config documented in README and shown in validation error messages for reference
- All errors shown at once (not fail-fast on first error)
- Validates: duplicate category names, missing 'name' field, invalid contact_type values, parent referencing non-existent category, circular parent chains, empty category list
- Destination mailbox existence validated separately (against live Fastmail)

### Claude's Discretion
- Pydantic model design for the category structure
- How defaults are represented in code (frozen list, factory function, etc.)
- Internal data structures for the resolved category mapping
- Error message formatting and wording
- Test structure and organization

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CONFIG-01 | Triage categories defined as a structured list (label, contact group, destination mailbox per category) | TriageCategory Pydantic model with derivation rules; `@model_validator` resolves all fields |
| CONFIG-02 | Categories configurable via `MAILROOM_TRIAGE_CATEGORIES` JSON environment variable | Pydantic-settings natively parses JSON strings for `list[BaseModel]` fields from env vars |
| CONFIG-03 | Default categories match v1.0 behavior (Imbox, Feed, PaperTrail, Jail, Person) so zero-config deployments work | Default factory function returning the 5 default TriageCategory instances |
| CONFIG-04 | All derived properties (triage labels, contact groups, required mailboxes) computed from category mapping | `@model_validator(mode='after')` builds lookup dicts from resolved category list |
| CONFIG-05 | User can add custom triage categories beyond the 5 defaults | Full replacement semantics: user provides complete list, any valid category accepted |
| CONFIG-06 | Startup validation rejects invalid category configurations (missing fields, duplicate labels) | `@model_validator(mode='after')` collects all errors before raising ValueError |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | >=2.0 (already installed via pydantic-settings) | Category model definition, field validation, model_validator | Already in use; BaseModel for TriageCategory |
| pydantic-settings | >=2.0 (already installed) | JSON env var parsing for `MAILROOM_TRIAGE_CATEGORIES` | Already in use; natively parses JSON strings for complex types |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none needed) | - | - | All required libraries are already in the project |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pydantic BaseModel for TriageCategory | TypedDict or dataclass | Pydantic gives free JSON parsing, validation, and error messages -- no reason to use anything else |
| `@model_validator` for cross-field checks | Multiple `@field_validator` calls | model_validator sees the full model, needed for parent references and duplicate detection |

**Installation:** No new packages needed. All dependencies are already in `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure
```
src/mailroom/core/
├── config.py           # MailroomSettings + TriageCategory + ResolvedCategory
└── logging.py          # (unchanged)
```

All new models live in `config.py` alongside `MailroomSettings`. No new files needed -- this is a config refactor, not a new module.

### Pattern 1: TriageCategory Input Model
**What:** A Pydantic BaseModel representing user input -- only `name` is required, everything else is optional with `None` defaults that trigger derivation.
**When to use:** This is the shape the user writes in their JSON config.
**Example:**
```python
from pydantic import BaseModel, field_validator
from typing import Literal

class TriageCategory(BaseModel):
    """A single triage category as provided by the user."""
    name: str
    label: str | None = None           # Derived: @To{NameNoSpaces}
    contact_group: str | None = None   # Derived: {Name}
    destination_mailbox: str | None = None  # Derived: {Name}
    contact_type: Literal["company", "person"] = "company"
    parent: str | None = None          # Optional: parent category name

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Category name must not be empty")
        return v.strip()
```

### Pattern 2: ResolvedCategory Dataclass
**What:** An immutable resolved category with all derived fields filled in. No Optional fields -- everything is concrete.
**When to use:** This is what the service logic consumes. Built by the model_validator after resolving defaults and parent inheritance.
**Example:**
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ResolvedCategory:
    """A fully resolved triage category -- all fields concrete."""
    name: str
    label: str               # e.g., "@ToImbox"
    contact_group: str        # e.g., "Imbox"
    destination_mailbox: str  # e.g., "Inbox"
    contact_type: str         # "company" or "person"
    parent: str | None        # parent category name (for Phase 7 setup script)
```

### Pattern 3: Model Validator for Resolution + Validation
**What:** `@model_validator(mode='after')` on MailroomSettings resolves defaults, applies parent inheritance, and validates constraints in one pass.
**When to use:** Always -- this runs at settings construction time.
**Example:**
```python
from pydantic import model_validator
from typing_extensions import Self

class MailroomSettings(BaseSettings):
    triage_categories: list[TriageCategory] = Field(
        default_factory=_default_categories
    )

    # Computed at validation time (not stored as fields)
    _resolved_categories: list[ResolvedCategory]
    _label_to_category: dict[str, ResolvedCategory]

    @model_validator(mode='after')
    def resolve_and_validate_categories(self) -> Self:
        errors: list[str] = []

        # 1. Check empty list
        if not self.triage_categories:
            errors.append("At least one triage category is required")

        # 2. Check duplicate names
        names = [c.name for c in self.triage_categories]
        dupes = [n for n in names if names.count(n) > 1]
        if dupes:
            errors.append(f"Duplicate category names: {', '.join(set(dupes))}")

        # 3. Resolve defaults (derive label, group, mailbox from name)
        # 4. Resolve parent inheritance
        # 5. Check parent references exist
        # 6. Check circular parent chains
        # 7. Check shared contact groups without parent relationship
        # 8. Check duplicate labels

        if errors:
            raise ValueError(
                "Invalid triage category configuration:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        # Build lookup dicts
        self._resolved_categories = resolved
        self._label_to_category = {r.label: r for r in resolved}
        return self
```

### Pattern 4: Derivation Rules
**What:** Pure functions that derive label, group, and mailbox from a category name.
**When to use:** During resolution in the model_validator.
**Example:**
```python
def derive_label(name: str) -> str:
    """Derive triage label from category name: 'Paper Trail' -> '@ToPaperTrail'"""
    return f"@To{''.join(name.split())}"

def derive_contact_group(name: str) -> str:
    """Derive contact group from category name: identity."""
    return name

def derive_destination_mailbox(name: str) -> str:
    """Derive destination mailbox from category name: identity."""
    return name
```

### Pattern 5: Default Categories Factory
**What:** A function that returns the 5 v1.0 default categories.
**When to use:** As `default_factory` for the `triage_categories` field.
**Example:**
```python
def _default_categories() -> list[TriageCategory]:
    """v1.0 default categories -- used when MAILROOM_TRIAGE_CATEGORIES is not set."""
    return [
        TriageCategory(name="Imbox", destination_mailbox="Inbox"),
        TriageCategory(name="Feed"),
        TriageCategory(name="Paper Trail"),
        TriageCategory(name="Jail"),
        TriageCategory(name="Person", parent="Imbox", contact_type="person"),
    ]
```

Note: Imbox needs an explicit `destination_mailbox="Inbox"` override because its derived default ("Imbox") differs from the actual Fastmail mailbox ("Inbox"). Person inherits from Imbox via `parent`, getting `contact_group="Imbox"` and `destination_mailbox="Inbox"`.

### Anti-Patterns to Avoid
- **Keeping old individual fields alongside new list:** Remove `label_to_imbox`, `label_to_feed`, `group_imbox`, etc. entirely. They become dead code that drifts from the real config.
- **Building the mapping as `dict[str, dict[str, str]]`:** Use typed `ResolvedCategory` objects instead of anonymous dicts. The workflow currently accesses `mapping["group"]`, `mapping["contact_type"]`, `mapping["destination_mailbox"]` -- these become `category.contact_group`, `category.contact_type`, `category.destination_mailbox`.
- **Validating errors one at a time (fail-fast):** User decision requires ALL errors shown at once. Collect into a list, raise once at the end.
- **Storing PrivateAttr for resolved data:** Use regular Python attributes set in model_validator (prefix with `_`) or use `model_config = ConfigDict(arbitrary_types_allowed=True)` with private attributes. Simplest approach: set `object.__setattr__(self, '_resolved_categories', resolved)` in the validator since Pydantic models are somewhat frozen after init.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON parsing from env var | Custom JSON.loads() parsing | Pydantic-settings native JSON parsing for complex types | Pydantic-settings already does this for `list[BaseModel]` fields |
| Field-level type validation | Manual isinstance checks | Pydantic type hints + `Literal["company", "person"]` | Pydantic gives free validation + clear error messages |
| Config error formatting | Custom error string building | Pydantic's `ValidationError` error list format | Pydantic already collects and formats multiple errors |

**Key insight:** Pydantic-settings already handles the hard part (JSON env var parsing). The phase is primarily about modeling the category structure, writing derivation logic, and replacing hardcoded references -- not plumbing.

## Common Pitfalls

### Pitfall 1: Pydantic-settings env_prefix with JSON field
**What goes wrong:** The env var name must match `{prefix}{field_name}`. With `env_prefix="MAILROOM_"` and field `triage_categories`, the env var is `MAILROOM_TRIAGE_CATEGORIES`.
**Why it happens:** Easy to forget the prefix or get case wrong.
**How to avoid:** pydantic-settings is case-insensitive by default (already configured). Just set `MAILROOM_TRIAGE_CATEGORIES='[...]'`.
**Warning signs:** Settings load with defaults even when env var is set (means the name didn't match).

### Pitfall 2: Default factory vs default value for mutable list
**What goes wrong:** Using `triage_categories: list[TriageCategory] = [...]` shares one mutable list across all instances.
**Why it happens:** Python default argument gotcha.
**How to avoid:** Always use `Field(default_factory=_default_categories)`.
**Warning signs:** Tests mutating settings affect each other.

### Pitfall 3: Parent resolution ordering
**What goes wrong:** If parent categories appear AFTER children in the list, resolving parent inheritance fails.
**Why it happens:** Linear iteration assumes parents already resolved.
**How to avoid:** Two-pass resolution: first pass resolves non-parent fields (name, label), second pass resolves parent inheritance. Or sort by dependency (categories without parents first). Two-pass is simpler and doesn't reorder user input.
**Warning signs:** "Parent not found" errors when parent is defined but appears later in list.

### Pitfall 4: Shared contact groups without parent relationship
**What goes wrong:** Two unrelated categories using the same contact_group would create ambiguity in already-grouped detection.
**Why it happens:** User manually sets `contact_group` to the same value on two categories.
**How to avoid:** Validate that no two categories share a `contact_group` unless one is a child of the other (via `parent` field).
**Warning signs:** Already-grouped detection triggers false positives or misses real conflicts.

### Pitfall 5: ScreenerWorkflow consuming dict vs typed object
**What goes wrong:** After refactoring config, the workflow still does `mapping["group"]` which fails with attribute-based access.
**Why it happens:** Forgetting to update all consumers.
**How to avoid:** Change `label_to_group_mapping` property to return `dict[str, ResolvedCategory]` and update all 3 access sites in `screener.py` (lines 303-305, 362-363). Also update tests.
**Warning signs:** KeyError or AttributeError at runtime.

### Pitfall 6: Imbox default destination_mailbox
**What goes wrong:** Derivation rule produces `destination_mailbox="Imbox"` for the Imbox category, but the actual Fastmail mailbox is `"Inbox"`.
**Why it happens:** Imbox is a special case where the category name differs from the Fastmail destination.
**How to avoid:** The default Imbox category MUST explicitly set `destination_mailbox="Inbox"`. The derivation rule is `name -> name`, which gives "Imbox" -- wrong for this case. This is handled by the explicit override in the default factory.
**Warning signs:** Startup crash: "Required mailboxes not found: Imbox".

## Code Examples

### Example 1: Complete TriageCategory Model
```python
from pydantic import BaseModel, field_validator
from typing import Literal

class TriageCategory(BaseModel):
    """User-facing triage category configuration."""
    name: str
    label: str | None = None
    contact_group: str | None = None
    destination_mailbox: str | None = None
    contact_type: Literal["company", "person"] = "company"
    parent: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Category name must not be empty")
        return v.strip()
```

### Example 2: Pydantic-settings JSON Env Var Parsing (verified)
```python
# Source: pydantic-settings docs - "Parsing environment variable values"
# Complex types like list, set, dict, and sub-models are populated from the
# environment by treating the environment variable's value as a JSON-encoded string.

# Setting this env var:
# MAILROOM_TRIAGE_CATEGORIES='[{"name": "Imbox", "destination_mailbox": "Inbox"}, {"name": "Receipts"}]'

# ...is automatically parsed into list[TriageCategory] by pydantic-settings.
# No custom parsing code needed.
```

### Example 3: Collecting All Validation Errors
```python
@model_validator(mode='after')
def resolve_and_validate_categories(self) -> Self:
    errors: list[str] = []
    cats = self.triage_categories

    if not cats:
        errors.append("At least one triage category is required.")

    # Check duplicate names
    seen_names: set[str] = set()
    for cat in cats:
        if cat.name in seen_names:
            errors.append(f"Duplicate category name: '{cat.name}'")
        seen_names.add(cat.name)

    # Check parent references
    name_set = {c.name for c in cats}
    for cat in cats:
        if cat.parent and cat.parent not in name_set:
            errors.append(
                f"Category '{cat.name}' references non-existent parent '{cat.parent}'"
            )

    # Check circular parent chains
    for cat in cats:
        if cat.parent:
            visited = {cat.name}
            current = cat.parent
            parent_map = {c.name: c.parent for c in cats}
            while current:
                if current in visited:
                    errors.append(f"Circular parent chain involving '{cat.name}'")
                    break
                visited.add(current)
                current = parent_map.get(current)

    if errors:
        default_json = json.dumps(
            [c.model_dump(exclude_none=True) for c in _default_categories()],
            indent=2,
        )
        raise ValueError(
            "Invalid triage category configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
            + f"\n\nDefault configuration for reference:\n{default_json}"
        )
    return self
```

### Example 4: Updating Workflow Consumers
```python
# BEFORE (v1.0 -- dict-based mapping):
mapping = self._settings.label_to_group_mapping[label_name]
group_name = mapping["group"]
contact_type = mapping["contact_type"]

# AFTER (v1.1 -- typed ResolvedCategory):
category = self._settings.label_to_category_mapping[label_name]
group_name = category.contact_group
contact_type = category.contact_type
```

### Example 5: Properties Derived from Resolved Categories
```python
@property
def triage_labels(self) -> list[str]:
    """All triage label names, derived from resolved categories."""
    return [c.label for c in self._resolved_categories]

@property
def contact_groups(self) -> list[str]:
    """Unique contact group names, derived from resolved categories."""
    return list({c.contact_group for c in self._resolved_categories})

@property
def required_mailboxes(self) -> list[str]:
    """All mailbox names that must exist at startup."""
    mailboxes = {"Inbox", self.screener_mailbox, self.label_mailroom_error}
    for c in self._resolved_categories:
        mailboxes.add(c.label)
        mailboxes.add(c.destination_mailbox)
    if self.warnings_enabled:
        mailboxes.add(self.label_mailroom_warning)
    return list(mailboxes)
```

## Codebase Impact Analysis

### Files That Must Change

| File | What Changes | Scope |
|------|-------------|-------|
| `src/mailroom/core/config.py` | New TriageCategory + ResolvedCategory models, remove 9 hardcoded fields, replace 4 properties, add model_validator | **Major** -- primary implementation |
| `src/mailroom/workflows/screener.py` | Update 3 sites accessing mapping dict to use ResolvedCategory attributes | Minor -- 3 lines change |
| `src/mailroom/__main__.py` | No changes needed (already uses `settings.required_mailboxes` and `settings.contact_groups`) | None |
| `tests/conftest.py` | Update `mock_settings` and `mock_mailbox_ids` fixtures | Moderate |
| `tests/test_config.py` | Rewrite most tests for new category structure, add validation tests | **Major** -- test rewrite |
| `tests/test_screener_workflow.py` | Update mock settings usage to work with new config shape | Moderate |

### Consumer Interface (what the rest of the code depends on)

The rest of the codebase depends on these MailroomSettings properties. They must continue to work:

| Property | Current Return Type | New Return Type | Breaking? |
|----------|-------------------|-----------------|-----------|
| `triage_labels` | `list[str]` | `list[str]` | No |
| `label_to_group_mapping` | `dict[str, dict[str, str]]` | `dict[str, ResolvedCategory]` | **Yes** -- consumers change from `["group"]` to `.contact_group` |
| `required_mailboxes` | `list[str]` | `list[str]` | No |
| `contact_groups` | `list[str]` | `list[str]` | No |
| `screener_mailbox` | `str` | `str` | No |
| `label_mailroom_error` | `str` | `str` | No |
| `label_mailroom_warning` | `str` | `str` | No |

Only `label_to_group_mapping` has a breaking interface change. There are exactly 3 consumer sites in `screener.py` to update.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Individual env vars per label/group | Structured JSON env var for full category list | This phase | Simpler config, extensible, no field explosion |
| `dict[str, str]` for mapping values | Typed frozen dataclass (ResolvedCategory) | This phase | Type safety, IDE autocomplete, no string key typos |
| Hardcoded 5-category logic | Data-driven N-category engine | This phase | Users can define any number of custom categories |

## Open Questions

1. **Private attributes vs regular attributes in model_validator**
   - What we know: Pydantic v2 models can use `PrivateAttr` for non-field attributes, or we can use `object.__setattr__` in the model_validator.
   - What's unclear: Cleanest way to store `_resolved_categories` and `_label_to_category` on the settings object.
   - Recommendation: Use `PrivateAttr` with `default=None` and set them in the model_validator. This is the Pydantic-blessed approach. Alternatively, make them regular computed properties that iterate the resolved list each time (acceptable since the list is small and accessed infrequently).

2. **Rename `label_to_group_mapping` property?**
   - What we know: The current name references "group" specifically, but the new return type is a full ResolvedCategory.
   - What's unclear: Whether to keep backward-compatible name or rename.
   - Recommendation: Rename to `label_to_category_mapping` to match the new semantics. Since consumers must be updated anyway (dict -> attribute access), renaming is free.

## Sources

### Primary (HIGH confidence)
- pydantic-settings docs (via Context7 /pydantic/pydantic-settings) -- JSON env var parsing for complex types, `env_prefix` behavior
- pydantic docs (via Context7 /pydantic/pydantic) -- `@model_validator(mode='after')`, `@field_validator`, `Literal` type, `ValidationError` handling
- Codebase analysis -- `src/mailroom/core/config.py`, `src/mailroom/workflows/screener.py`, `src/mailroom/__main__.py`, all test files

### Secondary (MEDIUM confidence)
- None needed -- all patterns verified via Context7 and existing codebase

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all patterns verified in existing pydantic/pydantic-settings docs
- Architecture: HIGH -- straightforward refactor of existing config module using established Pydantic patterns
- Pitfalls: HIGH -- identified from direct codebase analysis (exact line numbers of consumer sites)

**Research date:** 2026-02-26
**Valid until:** 2026-03-26 (stable domain -- Pydantic v2 patterns are mature)
