# Phase 11: Config Layer - Research

**Researched:** 2026-03-02
**Domain:** Pydantic config modeling, parent-chain resolution, additive JMAP mailbox filing
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- New defaults include Billboard (parent: Paper Trail) and Truck (parent: Paper Trail)
- Imbox gets `add_to_inbox: true` and its own `Imbox` mailbox (no longer `destination_mailbox: Inbox`)
- Person is fully independent: own mailbox `Person`, own contact group `Person`, own label `@ToPerson`
- Full new defaults:
  ```yaml
  categories:
    - name: Imbox
      add_to_inbox: true
    - Feed
    - Paper Trail
    - Jail
    - name: Person
      parent: Imbox
      contact_type: person
    - name: Billboard
      parent: Paper Trail
    - name: Truck
      parent: Paper Trail
  ```
- Child categories derive ALL fields from their own name: label, contact_group, destination_mailbox
- No field inheritance from parent whatsoever
- Parent relationship only means: additive contact groups + additive mailbox filing
- When a sender is triaged to a child category, they are added to the child's contact group AND all ancestor contact groups (full chain walk)
- When filing/sweeping emails, apply the child's destination mailbox AND all ancestor destination mailboxes
- `add_to_inbox` default: `false` (opt-in to Inbox visibility)
- `add_to_inbox` is per-category, NEVER inherited through parent chain
- `add_to_inbox` is Screener-only: only adds Inbox label to emails that are in Screener at triage time
- Re-triage does NOT re-add Inbox to existing emails (captured in RTRI-06 for Phase 13)
- `destination_mailbox: Inbox` is rejected at startup with helpful error message
- Sieve guidance shows ALL categories (root AND child), grouped by parent for readability, with syntax highlighting and prominent "Continue to apply other rules" note
- Setup CLI provisions separate mailbox and contact group for EACH category (root and child)
- `config.yaml.example` updated to show new defaults
- Already-grouped check deprecation happens in Phase 13, not Phase 11

### Claude's Discretion
- Exact validation error message wording (beyond CFG-02 which is specified)
- Color palette for sieve guidance syntax highlighting (extend existing cyan-based scheme)
- Internal implementation of parent chain walking (recursive vs iterative)
- Test structure and organization

### Deferred Ideas (OUT OF SCOPE)
- Investigate whether contact_group should always equal destination_mailbox (1:1 mapping) -- future investigation
- Already-grouped check removal -- happens in Phase 13 with re-triage support
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CFG-01 | Operator can set `add_to_inbox` per category to control Inbox visibility independently of destination mailbox (does not inherit through parent chain) | Add `add_to_inbox: bool = False` field to `TriageCategory` model and `ResolvedCategory` dataclass. Wire into `_get_destination_mailbox_ids` to conditionally add Inbox ID. Never propagate through parent chain. |
| CFG-02 | System rejects `destination_mailbox: Inbox` with clear error pointing to `add_to_inbox` flag | Add validation check in `_validate_categories()` that scans all categories for `destination_mailbox == "Inbox"` (both explicit and derived). Append error to collected errors list. |
| CFG-03 | Child categories resolve as fully independent categories (own label, contact group, destination mailbox derived from name) | Remove the second pass parent inheritance logic in `resolve_categories()`. Children keep their name-derived fields -- no field overwriting from parent. |
| CFG-04 | Parent relationship applies parent's label chain on triage (additive labels, not field inheritance) | Build `_get_parent_chain()` helper. Modify `_get_destination_mailbox_ids()` to walk the chain and return list of all ancestor destination mailbox IDs. Modify `_process_sender()` to call `upsert_contact` for each group in the chain. |
| CFG-05 | Circular parent references detected and rejected at startup validation | Already implemented in `_validate_categories()` check #4. No new work needed -- existing test coverage confirms. |
| CFG-06 | No backward compatibility -- config supports current format only, no migration shims or legacy fallbacks | New defaults replace old ones. No migration code. Breaking change is intentional. |
| CFG-07 | Setup CLI provisions independent mailbox and contact group for each child category | `plan_resources()` already iterates all `resolved_categories` including children. With CFG-03 making children independent, each child gets its own mailbox/group name, so provisioner picks them up automatically. Verify with tests. |
| CFG-08 | Sieve guidance output reflects additive parent label semantics | Rewrite `generate_sieve_guidance()` to include ALL categories (remove `parent is None` filter), add syntax highlighting colors, add "Continue to apply other rules" prominence, differentiate `add_to_inbox` vs. non-`add_to_inbox` rule templates. |
</phase_requirements>

## Summary

Phase 11 modifies the config layer to support independent child categories with additive parent chain behavior. The changes span five modules: `config.py` (model + resolution), `screener.py` (additive filing + additive contact groups), `sieve_guidance.py` (all-category display with `add_to_inbox` semantics), `colors.py` (extended color palette), and `config.yaml.example` (updated defaults).

The existing codebase is well-structured for this change. The two-pass resolution in `resolve_categories()` currently has a second pass that overwrites child fields with parent values -- this needs to be removed entirely. The `_get_destination_mailbox_ids()` method currently returns a single-element list and needs to walk the parent chain to return multiple IDs. The `_process_sender()` method currently calls `upsert_contact` once with a single group name and needs to call it for each group in the additive chain (or the CardDAV layer needs a multi-group upsert).

**Primary recommendation:** Implement in four layers: (1) config model changes + validation, (2) resolution logic changes, (3) screener workflow additive behavior, (4) sieve guidance + setup CLI verification. The existing test suite (280 tests, all passing) provides a solid safety net, but many tests encode the current parent-inheritance behavior and will need updating.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.x (via pydantic-settings) | Config validation and modeling | Already in use, `TriageCategory` is a BaseModel |
| pydantic-settings[yaml] | 2.x | YAML config loading | Already in use for `MailroomSettings` |
| structlog | latest | Structured logging | Already in use throughout |
| click | 8.1+ | CLI framework | Already in use for `mailroom setup` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | latest | Unit testing | Already configured in pyproject.toml |
| vobject | 0.9.9+ | CardDAV vCard parsing | Already in use for contact management |

No new libraries needed. All changes use existing dependencies.

## Architecture Patterns

### Recommended Change Map

```
src/mailroom/
├── core/
│   └── config.py          # TriageCategory + ResolvedCategory + resolution + validation
├── workflows/
│   └── screener.py        # _get_destination_mailbox_ids + _process_sender additive logic
├── setup/
│   ├── sieve_guidance.py  # All-category display with add_to_inbox differentiation
│   ├── colors.py          # Extended ANSI color palette
│   └── provisioner.py     # No changes needed (already iterates all categories)
├── cli.py                 # No changes needed
config.yaml.example        # Updated defaults
tests/
├── test_config.py         # Major updates (new defaults, no inheritance, add_to_inbox)
├── test_screener_workflow.py  # Additive chain tests
├── test_sieve_guidance.py     # All-category display tests
└── conftest.py            # Updated mock_mailbox_ids for new categories
```

### Pattern 1: Additive Parent Chain Walking

**What:** A utility to walk from a category up through its parent chain, collecting all ancestor categories.
**When to use:** Called by `_get_destination_mailbox_ids()` for mailbox IDs and by `_process_sender()` for contact group names.
**Recommendation:** Iterative loop is simpler and avoids recursion depth issues. Build into `config.py` as a standalone function or method on `MailroomSettings`.

```python
# Iterative parent chain walk
def get_parent_chain(category_name: str, resolved: dict[str, ResolvedCategory]) -> list[ResolvedCategory]:
    """Walk from category up through parents, returning [self, parent, grandparent, ...]."""
    chain: list[ResolvedCategory] = []
    current = resolved.get(category_name)
    while current:
        chain.append(current)
        if current.parent:
            current = resolved.get(current.parent)
        else:
            break
    return chain
```

The caller extracts what it needs from the chain:
- Destination mailbox IDs: `[resolved_id(c.destination_mailbox) for c in chain]`
- Contact group names: `[c.contact_group for c in chain]`

### Pattern 2: add_to_inbox as Screener-Only Conditional

**What:** The `add_to_inbox` flag only adds Inbox when the email is currently in Screener (initial triage). It is checked on the triaged category only, never inherited.
**When to use:** In `_get_destination_mailbox_ids()` or its replacement, when building the list of mailbox IDs to apply during sweep.
**Key detail:** This flag is checked on the *triaged* category (the one whose label was applied), NOT on ancestors in the chain. If Person (child of Imbox) is triaged and Person does NOT have `add_to_inbox`, Inbox is NOT added -- even though the additive chain includes Imbox which does have the flag.

```python
def _get_destination_mailbox_ids(self, label_name: str, from_screener: bool = True) -> list[str]:
    """Return mailbox IDs for additive filing."""
    category = self._settings.label_to_category_mapping[label_name]
    chain = get_parent_chain(category.name, self._category_map)

    ids = [self._mailbox_ids[c.destination_mailbox] for c in chain]

    # add_to_inbox: only on the triaged category, only from Screener
    if category.add_to_inbox and from_screener:
        inbox_id = self._mailbox_ids["Inbox"]
        if inbox_id not in ids:
            ids.append(inbox_id)

    return ids
```

### Pattern 3: Collect-All-Errors Validation

**What:** The existing validation pattern collects all errors before raising, so operators see all problems at once.
**When to use:** Extend `_validate_categories()` with CFG-02 check in the same pattern.

```python
# Add to _validate_categories after existing checks:
# 7. destination_mailbox: Inbox banned
for cat in categories:
    dest = cat.destination_mailbox if cat.destination_mailbox is not None else derive_destination_mailbox(cat.name)
    if dest == "Inbox":
        errors.append(
            f"Category '{cat.name}' has destination_mailbox: Inbox. "
            f"Use add_to_inbox: true instead to make emails appear in Inbox."
        )
```

### Pattern 4: Additive Contact Group Upsert

**What:** When processing a sender, add them to all groups in the parent chain (child + parent + grandparent ...).
**When to use:** In `_process_sender()` during the contact upsert step.
**Key design decision:** The current `upsert_contact()` API accepts a single `group_name`. For additive groups, the simplest approach is to call `upsert_contact` once for the primary group (which handles create-or-find + name management) and then call a simpler `add_to_group()` for each additional ancestor group.

```python
# In _process_sender:
chain = get_parent_chain(category.name, self._category_map)
# Primary upsert: handles contact creation and name management
result = self._carddav.upsert_contact(sender, display_name, chain[0].contact_group, contact_type=contact_type)
# Additive: add to ancestor groups (skip first, already done)
for ancestor in chain[1:]:
    self._carddav.add_to_group(contact_uid, ancestor.contact_group)
```

Note: Need to check if `add_to_group` exists on CardDAVClient or needs adding. The `upsert_contact` method returns a dict with `uid` -- that can be used for subsequent `add_to_group` calls.

### Anti-Patterns to Avoid

- **Inheriting `add_to_inbox` through the parent chain:** The flag is per-category only. Even if a parent has it, children do not inherit it. This is a locked design decision.
- **Using `destination_mailbox: Inbox` for inbox visibility:** This is explicitly banned by CFG-02. Always use `add_to_inbox: true` instead.
- **Single-mailbox filing assumption:** The current `_get_destination_mailbox_ids` returns a single-element list. After Phase 11, it can return multiple IDs. All callers already handle lists (e.g., `batch_move_emails` takes `add_mailbox_ids: list[str]`), so this is safe.
- **Filtering sieve guidance to root-only categories:** The current code filters `cat.parent is None`. Phase 11 must show ALL categories for the 1:1 group-to-mailbox sieve rule pattern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ANSI terminal color detection | Custom isatty checks | Existing `colors.py` `use_color()` | Already handles `NO_COLOR` env var and TTY detection |
| Config validation | Custom error collection | Existing `_validate_categories()` pattern | Collects all errors, includes defaults in error message |
| YAML parsing | Custom parser | pydantic-settings `YamlConfigSettingsSource` | Already wired up in `MailroomSettings.settings_customise_sources` |
| Circular reference detection | New cycle detection | Existing check #4 in `_validate_categories()` | Already handles self-reference and multi-hop cycles |

**Key insight:** Almost all infrastructure needed already exists. The work is modifying behavior, not building new systems.

## Common Pitfalls

### Pitfall 1: Breaking Existing Tests Silently
**What goes wrong:** The current test suite (280 tests) encodes the v1.0 parent-inheritance behavior. Many tests assert that Person inherits Imbox's contact_group and destination_mailbox.
**Why it happens:** The behavior change from "inherit parent fields" to "independent children" is a fundamental shift in resolution logic.
**How to avoid:** Update tests in lockstep with code changes. Specifically:
- `TestParentInheritance` class: assertions change from `person.contact_group == "Imbox"` to `person.contact_group == "Person"`
- `TestComputedProperties.test_label_category_mapping`: Person's contact_group/destination_mailbox assertions change
- `TestComputedProperties.test_contact_groups_unique`: count changes from 4 to 7 (all categories get independent groups)
- `conftest.py mock_mailbox_ids`: needs new entries for Person, Billboard, Truck mailboxes
- `test_screener_workflow.py`: @ToPerson tests currently assert sweep to `mb-inbox` -- must change to additive chain

**Warning signs:** Tests fail with assertion errors on contact_group or destination_mailbox values.

### Pitfall 2: add_to_inbox Inheritance Leaking Through Parent Chain
**What goes wrong:** Implementing additive mailbox filing but accidentally also propagating add_to_inbox through the chain.
**Why it happens:** When walking the parent chain for mailbox IDs, it's tempting to check each ancestor's `add_to_inbox`.
**How to avoid:** Only check `add_to_inbox` on the *triaged* category (the one whose label was applied). Never check ancestors.
**Warning signs:** Emails triaged to Person (child of Imbox with `add_to_inbox: true`) getting Inbox when they shouldn't.

### Pitfall 3: Shared Contact Group Validation False Positive
**What goes wrong:** After removing parent inheritance, children have independent contact groups. The existing validation check #6 (shared contact groups without parent relationship) might false-positive if someone explicitly sets `contact_group` to match a parent.
**Why it happens:** The validation allows shared groups when categories are related via parent. This still works correctly for the new model.
**How to avoid:** The existing validation logic already checks `cat_a.parent != b and cat_b.parent != a`. This remains correct. No change needed.

### Pitfall 4: Sieve Guidance Showing Duplicate or Confusing Rules
**What goes wrong:** With all categories shown (7 instead of 4), the sieve guidance could be overwhelming or unclear.
**Why it happens:** No grouping or visual hierarchy to show parent-child relationships.
**How to avoid:** Group child categories under their parent in the output. Use indentation or labels to show the relationship. The user specifically asked for "grouped by parent for readability."

### Pitfall 5: CardDAV Multi-Group Upsert Ordering
**What goes wrong:** If additive contact group addition fails partway through the chain, some groups have the contact and others don't.
**Why it happens:** Multiple CardDAV calls needed for additive groups (one per ancestor).
**How to avoid:** The primary `upsert_contact` handles the triaged category's group. Additional ancestor groups are additive -- partial success is acceptable because the triage label stays until the full operation succeeds (retry safety from TRIAGE-06). If the exception propagates, the whole sender retries next poll.

### Pitfall 6: Default Categories Change Breaks Test Fixtures
**What goes wrong:** `_default_categories()` changes from 5 to 7 categories, with Imbox losing `destination_mailbox: Inbox` override. Fixtures that hardcode 5 categories or Imbox->Inbox mapping break.
**Why it happens:** Many tests rely on `_default_categories()` implicitly via `MailroomSettings()` with empty config.
**How to avoid:** Update `_default_categories()` early. Then fix all test fixtures that depend on category count, names, or Imbox's destination_mailbox being "Inbox".
**Warning signs:** Tests failing with `IndexError`, `KeyError`, or wrong category count assertions.

## Code Examples

### Updated TriageCategory Model
```python
class TriageCategory(BaseModel):
    name: str
    label: str | None = None
    contact_group: str | None = None
    destination_mailbox: str | None = None
    contact_type: Literal["company", "person"] = "company"
    parent: str | None = None
    add_to_inbox: bool = False  # NEW: CFG-01
```

### Updated ResolvedCategory Dataclass
```python
@dataclass(frozen=True)
class ResolvedCategory:
    name: str
    label: str
    contact_group: str
    destination_mailbox: str
    contact_type: str
    parent: str | None
    add_to_inbox: bool  # NEW: CFG-01
```

### Updated _default_categories
```python
def _default_categories() -> list[TriageCategory]:
    return [
        TriageCategory(name="Imbox", add_to_inbox=True),
        TriageCategory(name="Feed"),
        TriageCategory(name="Paper Trail"),
        TriageCategory(name="Jail"),
        TriageCategory(name="Person", parent="Imbox", contact_type="person"),
        TriageCategory(name="Billboard", parent="Paper Trail"),
        TriageCategory(name="Truck", parent="Paper Trail"),
    ]
```

### Updated resolve_categories (no parent inheritance)
```python
def resolve_categories(categories: list[TriageCategory]) -> list[ResolvedCategory]:
    errors = _validate_categories(categories)
    if errors:
        # ... existing error formatting ...
        raise ValueError(...)

    # Single pass: derive all fields from own name (no parent inheritance)
    resolved: list[ResolvedCategory] = []
    for cat in categories:
        resolved.append(ResolvedCategory(
            name=cat.name,
            label=cat.label if cat.label is not None else derive_label(cat.name),
            contact_group=(
                cat.contact_group if cat.contact_group is not None
                else derive_contact_group(cat.name)
            ),
            destination_mailbox=(
                cat.destination_mailbox if cat.destination_mailbox is not None
                else derive_destination_mailbox(cat.name)
            ),
            contact_type=cat.contact_type,
            parent=cat.parent,
            add_to_inbox=cat.add_to_inbox,
        ))
    return resolved
```

### Parent Chain Walk Utility
```python
def get_parent_chain(
    category_name: str,
    resolved_map: dict[str, ResolvedCategory],
) -> list[ResolvedCategory]:
    """Return [self, parent, grandparent, ...] chain for a category."""
    chain: list[ResolvedCategory] = []
    current = resolved_map.get(category_name)
    while current:
        chain.append(current)
        current = resolved_map.get(current.parent) if current.parent else None
    return chain
```

### Updated _get_destination_mailbox_ids (additive chain)
```python
def _get_destination_mailbox_ids(self, label_name: str) -> list[str]:
    category = self._settings.label_to_category_mapping[label_name]
    resolved_map = {c.name: c for c in self._settings.resolved_categories}
    chain = get_parent_chain(category.name, resolved_map)

    ids = [self._mailbox_ids[c.destination_mailbox] for c in chain]

    # add_to_inbox: per-category only, Screener-only
    if category.add_to_inbox:
        inbox_id = self._mailbox_ids["Inbox"]
        if inbox_id not in ids:
            ids.append(inbox_id)

    return ids
```

### Extended Colors for Sieve Guidance
```python
# colors.py additions
BLUE = "\033[34m"
MAGENTA = "\033[35m"
BOLD = "\033[1m"
```

### Sieve Guidance Rule Templates
```
# Standard category (no add_to_inbox) -- 3 actions:
#   1. Add label: {destination_mailbox}
#   2. Archive (remove Inbox label)
#   3. Continue to apply other rules

# Category with add_to_inbox: true -- 2 actions:
#   1. Add label: {destination_mailbox}
#   2. Continue to apply other rules (NO archive)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `destination_mailbox: Inbox` on Imbox | `add_to_inbox: true` + own Imbox mailbox | Phase 11 (v1.2) | Inbox visibility decoupled from destination |
| Child inherits parent's contact_group + destination_mailbox | Child is fully independent, parent chain is additive only | Phase 11 (v1.2) | Simpler 1:1 sieve rules, each group maps to exactly one mailbox |
| Sieve guidance shows root categories only | Sieve guidance shows all categories | Phase 11 (v1.2) | Operators see every rule they need to create |
| 5 default categories | 7 default categories (add Billboard, Truck) | Phase 11 (v1.2) | More granular sorting out of the box |

**Deprecated/outdated:**
- `destination_mailbox: Inbox` on any category: rejected at startup with CFG-02 error
- Parent field inheritance: removed entirely from `resolve_categories()`
- Root-only sieve guidance filtering: removed in `generate_sieve_guidance()`

## Open Questions

1. **CardDAV `add_to_group` method availability**
   - What we know: `upsert_contact()` handles a single group. Additive groups need the contact added to multiple groups.
   - What's unclear: Whether `CardDAVClient` already has an `add_to_group(uid, group_name)` method, or if this needs to be built.
   - Recommendation: Check `CardDAVClient` during implementation. If missing, it's a thin wrapper around the existing group-member-add logic already in `upsert_contact`. Extract into a separate method.

2. **MailroomSettings resolved_map for chain walking**
   - What we know: `_get_destination_mailbox_ids` needs a `dict[str, ResolvedCategory]` map for chain walking. Currently `label_to_category_mapping` maps labels to categories.
   - What's unclear: Best place to expose a name-to-category map.
   - Recommendation: Add a `_name_to_category` property on `MailroomSettings` (built alongside `_label_to_category` in `resolve_and_validate_categories`). Or pass the resolved list and build the map in the utility function.

3. **Sieve guidance color scheme specifics**
   - What we know: User wants "more colors" and "syntax-highlighted feel" -- comments in gray, keywords colored, category names colored.
   - What's unclear: Exact color assignments (which ANSI colors for which elements).
   - Recommendation: Claude's discretion per CONTEXT.md. Suggest: category names in BOLD, mailbox names in CYAN, sieve keywords in MAGENTA, comments in DIM, `add_to_inbox` marker in GREEN.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all affected source files
- `config.py` (core/config.py): TriageCategory, ResolvedCategory, resolve_categories, _validate_categories, _default_categories
- `screener.py` (workflows/screener.py): _get_destination_mailbox_ids, _process_sender, poll
- `sieve_guidance.py` (setup/sieve_guidance.py): generate_sieve_guidance, _highlight_folder
- `colors.py` (setup/colors.py): ANSI color constants, use_color
- `provisioner.py` (setup/provisioner.py): plan_resources, apply_resources
- `docs/WIP.md`: Complete v1.2 workflow documentation with examples
- `config.yaml.example`: Current default config

### Secondary (MEDIUM confidence)
- Test file analysis (280 tests, all passing) for understanding current behavior contracts
- `conftest.py` for fixture patterns and mock_mailbox_ids structure

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries, all changes use existing dependencies
- Architecture: HIGH - Patterns directly derived from existing codebase analysis with clear modification paths
- Pitfalls: HIGH - Identified from concrete test assertions and code patterns that will break

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (stable internal codebase, no external API changes)
