# Phase 14: Contact Provenance Tracking for Clean Reset - Research

**Researched:** 2026-03-04
**Domain:** CardDAV contact provenance, config restructuring, reset workflow evolution
**Confidence:** HIGH

## Summary

Phase 14 adds provenance tracking to distinguish contacts Mailroom created from those it merely annotated (adopted). This enables the reset command to DELETE created contacts while only stripping notes from pre-existing ones. The phase also renames the `labels:` config section to `mailroom:`, adds a provenance contact group, fixes @MailroomWarning accumulation in the triage pipeline, and evolves the reset workflow with provenance-aware behavior including user-modification detection.

The codebase is well-structured for these changes. The `upsert_contact()` method already returns `action: "created"` vs `action: "existing"` -- the exact decision point for provenance group membership. The `add_to_group()` method handles group membership with ETag-based concurrency. The `plan_reset()`/`apply_reset()` pipeline needs significant evolution but follows clear patterns. No new external libraries are needed.

**Primary recommendation:** Implement in three waves: (1) config rename + provenance group creation in CardDAV/setup, (2) provenance tracking in triage pipeline + note format update + @MailroomWarning cleanup, (3) provenance-aware reset with user-modification detection and contact deletion.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Dedicated CardDAV contact group for provenance tracking (not note-based heuristic)
- Group populated only when `create_contact()` fires (action: "created")
- Pre-existing contacts that get upserted are NEVER added to provenance group
- No retroactive migration -- provenance tracking starts from this phase forward
- Provenance group membership is permanent across re-triage (creation origin doesn't change)
- Provenance group is invisible to triage pipeline: not in `resolved_categories`, not checked by `check_membership()`, not in sieve guidance
- Note format adds provenance line after header: "Created by Mailroom" or "Adopted by Mailroom"
- Config: rename top-level `labels:` to `mailroom:`, rename keys (`mailroom_error` -> `label_error`, `mailroom_warning` -> `label_warning`), add `provenance_group` key
- No backward compatibility -- app fails to start if config doesn't match
- Single provenance group (note differentiates created vs adopted)
- Validated at startup alongside category groups (fail fast if missing)
- Setup CLI creates provenance group with `--apply`, reports as `kind="mailroom"`
- Reset: provenance + unmodified -> DELETE; provenance + user-modified -> WARN (strip note, remove from groups, apply @MailroomWarning to emails); no provenance + Mailroom note -> strip note, remove from groups
- "User-modified" = extra vCard fields beyond what Mailroom sets (FN, EMAIL, NOTE, UID, N, ORG)
- Reset operation order: (1) remove managed labels, (2) remove warning+error from ALL emails, (3) remove from category groups, (4) apply @MailroomWarning to modified provenance contacts' emails, (5) remove warned from provenance group, (6) strip notes, (7) delete unmodified provenance contacts
- @MailroomWarning cleanup on every successful triage: remove from ALL sender emails, reapply if condition persists
- Sieve guidance does NOT mention provenance group

### Claude's Discretion
- Default provenance group name (likely "Mailroom" for brevity)
- Exact "user-modified" detection logic (which vCard fields to compare)
- Implementation details for @MailroomWarning removal during triage
- Test structure and organization

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| vobject | >=0.9.9 | vCard parsing/serialization for contact operations | Already in use throughout CardDAV client |
| httpx | latest | HTTP client for CardDAV DELETE operations | Already in use for all CardDAV/JMAP operations |
| pydantic | v2 | Config model validation (rename labels -> mailroom) | Already powers MailroomSettings |
| pydantic-settings[yaml] | latest | YAML config loading | Already configured |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | latest | Structured logging for provenance events | Already in use in ScreenerWorkflow |
| pytest | latest | Unit tests | Already configured |

### Alternatives Considered
None needed -- all required libraries are already in the project.

**Installation:**
No new dependencies required.

## Architecture Patterns

### Recommended Change Map
```
src/mailroom/
  core/
    config.py          # Rename LabelSettings -> MailroomSettings section
  clients/
    carddav.py         # Add delete_contact(), provenance note format, provenance group add
  workflows/
    screener.py        # @MailroomWarning cleanup in _process_sender, provenance group plumbing
  setup/
    provisioner.py     # Add provenance group to plan_resources/apply_resources
  reset/
    resetter.py        # Provenance-aware plan/apply with DELETE + user-modified detection
    reporting.py       # Updated output for provenance-aware reset plan
tests/
  conftest.py          # Update mock_mailbox_ids fixture
  test_config.py       # Config rename tests
  test_resetter.py     # Provenance-aware reset tests
  test_screener_workflow.py  # @MailroomWarning cleanup tests
config.yaml.example   # Updated with mailroom: section
```

### Pattern 1: Provenance Group as Infrastructure (Not Triage)

**What:** The provenance group exists alongside category groups but is NOT part of the triage pipeline. It is an internal tracking mechanism managed by `upsert_contact()` and consumed by the reset module.

**When to use:** Any time a new contact is created via `create_contact()`.

**Key implementation detail:** The provenance group must be in `carddav._groups` for `add_to_group()` to work, but must NOT appear in `settings.contact_groups` (which drives `check_membership()` and sieve guidance). This means `validate_groups()` needs to be called with the provenance group included separately, or the provenance group needs to be added to `_groups` independently.

**Recommended approach:** Extend `validate_groups()` call in the startup path to include the provenance group name. The `_groups` dict is used internally by `add_to_group()` and `remove_from_group()` -- it just needs the group's href/etag/uid. The `contact_groups` property on settings remains triage-only.

```python
# In startup (screener __main__.py or similar):
all_groups = settings.contact_groups + [settings.mailroom.provenance_group]
carddav.validate_groups(all_groups)

# In check_membership() -- provenance group is already excluded because
# it iterates over self._groups but check_membership() is only called
# with exclude_group context. However, we need to ensure it's NOT
# returned as a "current group" during re-triage detection.
```

**CRITICAL SUBTLETY:** `check_membership()` iterates over ALL `self._groups`. If the provenance group is in `_groups`, `check_membership()` will find contacts in it and return it as their "group," breaking re-triage detection. Two solutions:

1. **Exclude provenance group in check_membership():** Pass it as a permanent exclude, or add a `triage_groups_only` parameter.
2. **Separate provenance group storage:** Store provenance group info separately from `_groups`, and use a dedicated method for provenance operations.

**Recommendation:** Option 1 is simpler. Add an `infrastructure_groups` set to CardDAVClient that `check_membership()` automatically skips. The provenance group is added to `_groups` for `add_to_group()`/`remove_from_group()` to work, but `check_membership()` skips groups in `infrastructure_groups`.

### Pattern 2: Config Section Rename (labels -> mailroom)

**What:** Rename the top-level `labels:` YAML section to `mailroom:` and rename internal keys.

**Current state:**
```python
class LabelSettings(BaseModel):
    mailroom_error: str = "@MailroomError"
    mailroom_warning: str = "@MailroomWarning"
    warnings_enabled: bool = True

class MailroomSettings(BaseSettings):
    labels: LabelSettings = LabelSettings()
```

**Target state:**
```python
class MailroomSectionSettings(BaseModel):
    label_error: str = "@MailroomError"
    label_warning: str = "@MailroomWarning"
    warnings_enabled: bool = True
    provenance_group: str = "Mailroom"

class MailroomSettings(BaseSettings):
    mailroom: MailroomSectionSettings = MailroomSectionSettings()
```

**Impact analysis -- all references to `settings.labels.*`:**
- `screener.py:178` -- `self._settings.labels.mailroom_error`
- `screener.py:279` -- `self._settings.labels.mailroom_error`
- `screener.py:328` -- `self._settings.labels.mailroom_warning`
- `screener.py:419` -- `self._settings.labels.warnings_enabled`
- `config.py:398` -- `self.labels.mailroom_error` (in `required_mailboxes`)
- `config.py:403` -- `self.labels.warnings_enabled` and `self.labels.mailroom_warning`
- `resetter.py:68` -- `settings.triage.screener_mailbox` (no labels ref here, but uses settings)
- Config YAML: `labels:` section

All change to `settings.mailroom.label_error`, `settings.mailroom.label_warning`, etc.

### Pattern 3: CardDAV DELETE for Contact Deletion

**What:** HTTP DELETE with If-Match ETag header to remove a vCard resource.

**Implementation:**
```python
def delete_contact(self, href: str, etag: str) -> None:
    """Delete a contact vCard from the addressbook.

    Uses If-Match for concurrency safety.

    Args:
        href: The vCard resource href (path).
        etag: Current ETag for concurrency control.

    Raises:
        httpx.HTTPStatusError: On HTTP errors.
    """
    self._require_connection()
    resp = self._http.delete(
        f"https://{self._hostname}{href}",
        headers={"If-Match": etag},
    )
    resp.raise_for_status()
```

This follows the same pattern as `update_contact_vcard()` but uses DELETE instead of PUT. CardDAV (WebDAV) DELETE is a standard operation (RFC 4918 Section 9.6).

### Pattern 4: User-Modified Detection

**What:** Determine if a user has added fields to a Mailroom-created contact beyond what Mailroom sets.

**Fields Mailroom sets on creation** (from `create_contact()`):
- `UID` -- always set
- `FN` -- always set
- `N` -- always set (empty for company, parsed for person)
- `EMAIL` -- always set (single entry)
- `NOTE` -- always set (Mailroom header + triage history)
- `ORG` -- set for company contacts only
- `VERSION` -- set by vobject automatically

**User-modified indicators** (extra fields that Mailroom never creates):
- `TEL` (phone number)
- `ADR` (address)
- `URL` (website)
- `PHOTO` (image)
- `BDAY` (birthday)
- `TITLE` (job title)
- `NICKNAME`
- Additional `EMAIL` entries beyond the one Mailroom created
- Any `X-` custom properties (except `X-ADDRESSBOOKSERVER-*`)

**Recommended detection logic:**
```python
MAILROOM_MANAGED_FIELDS = {
    "version", "uid", "fn", "n", "email", "note", "org",
    "prodid",  # vobject adds this
}

def _is_user_modified(vcard_data: str) -> bool:
    """Check if a contact has fields beyond what Mailroom creates."""
    card = vobject.readOne(vcard_data)
    content_keys = {k.lower() for k in card.contents.keys()}
    extra_fields = content_keys - MAILROOM_MANAGED_FIELDS
    if extra_fields:
        return True
    # Also check for multiple EMAIL entries (Mailroom creates exactly one)
    email_count = len(card.contents.get("email", []))
    if email_count > 1:
        return True
    return False
```

### Pattern 5: @MailroomWarning Cleanup in Triage Pipeline

**What:** On every successful triage, remove @MailroomWarning from ALL emails of that sender, then conditionally reapply if warning condition persists.

**Integration point:** `_process_sender()` in screener.py, before step 3a (warning label application).

**Implementation approach:**
```python
# In _process_sender(), after upsert_contact() but before warning check:
# Remove @MailroomWarning from ALL sender emails (idempotent cleanup)
warning_id = self._mailbox_ids.get(self._settings.mailroom.label_warning)
if warning_id and self._settings.mailroom.warnings_enabled:
    all_sender_emails = self._jmap.query_emails_by_sender(sender)
    if all_sender_emails:
        self._jmap.batch_remove_labels(all_sender_emails, [warning_id])

# ... then later, the existing name_mismatch check reapplies if needed
```

**Note:** `_reconcile_email_labels()` already fetches all sender emails via `query_emails_by_sender()`. The warning cleanup could be integrated there to avoid a redundant query. However, the separation is cleaner: warning cleanup is a pre-step, reconciliation is the main label step.

**Optimization:** Since `_reconcile_email_labels()` already fetches `all_email_ids = self._jmap.query_emails_by_sender(sender)`, we could pass those IDs to the warning cleanup to avoid a duplicate query. But since `_reconcile_email_labels` returns count (not IDs), this would require refactoring. Simplest approach: do the cleanup as a separate step before reconciliation, accepting the extra query. The cost is one additional JMAP call per sender, which is negligible for the typical use case.

### Anti-Patterns to Avoid
- **Adding provenance group to `resolved_categories`:** This would make it appear in sieve guidance, label scanning, and triage detection. It must stay separate.
- **Note-based provenance detection:** The CONTEXT.md explicitly chose a group-based approach over note heuristics. Notes can be edited by users, groups cannot (outside Mailroom).
- **Retroactive migration:** The decision is explicit: no backfill. New contacts get tracked, old ones don't.
- **Backward compatible config:** No migration shims. Old `labels:` config must be updated to `mailroom:` or the app fails to start.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| vCard field parsing | Custom vCard parser | `vobject.readOne()` | Already used everywhere, handles all edge cases |
| ETag concurrency | Custom locking | `If-Match`/`If-None-Match` headers | Standard WebDAV pattern already established |
| Group membership tracking | Database/file tracking | CardDAV contact group | Leverages existing infrastructure, survives restarts |
| Config validation | Manual field checking | Pydantic model validators | Already the pattern for all config |

**Key insight:** The provenance group is essentially using CardDAV as a persistent set data structure. It's the right choice because it survives container restarts, is atomic via ETags, and uses existing infrastructure.

## Common Pitfalls

### Pitfall 1: check_membership() Finding Provenance Group
**What goes wrong:** `check_membership()` iterates all `self._groups`. If provenance group is in `_groups`, it returns "Mailroom" as the sender's group, breaking re-triage detection.
**Why it happens:** `validate_groups()` stores all validated groups in `_groups`, and `check_membership()` iterates them all.
**How to avoid:** Either (a) add an `infrastructure_groups` exclusion set, or (b) always pass provenance group name as `exclude_group` in `_detect_retriage()`. Option (a) is safer -- it prevents any code path from accidentally treating provenance as a triage group.
**Warning signs:** Re-triage detection returning "Mailroom" as `old_group`, causing category lookup failures.

### Pitfall 2: Config Rename Breaking All References
**What goes wrong:** Renaming `labels` -> `mailroom` without updating all references causes AttributeError at runtime.
**Why it happens:** Multiple files reference `settings.labels.mailroom_error`, `settings.labels.mailroom_warning`, and `settings.labels.warnings_enabled`.
**How to avoid:** Use grep to find ALL references before renaming. The list: screener.py (4 refs), config.py (3 refs), config.yaml.example, all test files that create mock settings.
**Warning signs:** Test failures immediately reveal missed references.

### Pitfall 3: Reset Operation Order Matters
**What goes wrong:** Deleting contacts before removing them from groups leaves orphaned member references in group vCards. Or stripping notes before checking provenance makes it impossible to determine if a contact was adopted.
**Why it happens:** The CONTEXT.md specifies a precise 7-step order for good reason.
**How to avoid:** Follow the exact order: labels -> error/warning cleanup -> group removal -> warning application for modified -> provenance group removal -> note stripping -> contact deletion.
**Warning signs:** Group vCards referencing deleted contact UIDs, or contacts losing their note before the reset logic can inspect it.

### Pitfall 4: conftest.py and Mock Fixture Updates
**What goes wrong:** Tests fail because `mock_settings` still uses old `labels` section, or `mock_mailbox_ids` doesn't include new mailroom resources.
**Why it happens:** The conftest.py fixtures create MailroomSettings with default config. Renaming the config section changes defaults.
**How to avoid:** Update config.yaml.example first, then update conftest.py, then update individual test files.

### Pitfall 5: Provenance Group Not in _groups During Reset
**What goes wrong:** The reset module needs to call `remove_from_group()` and `get_group_members()` on the provenance group, but these methods require the group to be in `self._groups`.
**Why it happens:** `run_reset()` calls `carddav.validate_groups(settings.contact_groups)` which only includes triage groups.
**How to avoid:** In `run_reset()`, validate groups with provenance group included: `carddav.validate_groups(settings.contact_groups + [settings.mailroom.provenance_group])`.

## Code Examples

### CardDAV DELETE Contact
```python
# Source: RFC 4918 Section 9.6 + existing project patterns
def delete_contact(self, href: str, etag: str) -> None:
    """Delete a contact vCard from the addressbook."""
    self._require_connection()
    resp = self._http.delete(
        f"https://{self._hostname}{href}",
        headers={"If-Match": etag},
    )
    resp.raise_for_status()
```

### Provenance Group Membership in upsert_contact()
```python
# In upsert_contact(), after create_contact() succeeds:
if not results:
    new_contact = self.create_contact(
        email, display_name, contact_type=contact_type,
        group_name=group_name,
    )
    self.add_to_group(group_name, new_contact["uid"])
    # NEW: Add to provenance group if configured
    if provenance_group:
        self.add_to_group(provenance_group, new_contact["uid"])
    return {
        "action": "created",
        "uid": new_contact["uid"],
        "group": group_name,
        "name_mismatch": False,
    }
```

### Updated Note Format with Provenance Line
```python
# In create_contact(), new note format:
card.add("note").value = (
    f"\u2014 Mailroom \u2014\n"
    f"Created by Mailroom\n"
    f"Triaged to {group_name} on {date.today().isoformat()}"
)

# In upsert_contact() for existing contacts, when adding Mailroom section:
new_note = f"{mailroom_header}\nAdopted by Mailroom\n{retriage_entry}"
```

### User-Modified Detection
```python
# Fields that Mailroom manages on created contacts
MAILROOM_MANAGED_FIELDS = {
    "version", "uid", "fn", "n", "email", "note", "org", "prodid",
}

def _is_user_modified(vcard_data: str) -> bool:
    """Check if contact has fields beyond what Mailroom creates."""
    card = vobject.readOne(vcard_data)
    content_keys = {k.lower() for k in card.contents.keys()}
    extra = content_keys - MAILROOM_MANAGED_FIELDS
    if extra:
        return True
    # Multiple emails = user added one
    if len(card.contents.get("email", [])) > 1:
        return True
    return False
```

### Config Model Rename
```python
class MailroomSectionSettings(BaseModel):
    """Mailroom infrastructure label and group configuration."""
    label_error: str = "@MailroomError"
    label_warning: str = "@MailroomWarning"
    warnings_enabled: bool = True
    provenance_group: str = "Mailroom"

class MailroomSettings(BaseSettings):
    # ... credentials ...
    polling: PollingSettings = PollingSettings()
    triage: TriageSettings = TriageSettings()
    mailroom: MailroomSectionSettings = MailroomSectionSettings()  # was: labels
    logging: LoggingSettings = LoggingSettings()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `likely_created` heuristic in reset | Provenance group membership (deterministic) | Phase 14 | Clean DELETE vs uncertain "likely" suggestion |
| `settings.labels.*` | `settings.mailroom.*` | Phase 14 | All code referencing labels section must update |
| @MailroomWarning accumulates forever | Cleaned on each successful triage | Phase 14 | Warning labels become transient, not permanent |
| Reset strips notes only | Reset DELETEs created, strips adopted, WARNs modified | Phase 14 | Full cleanup capability |

**Deprecated/outdated:**
- `LabelSettings` class name -> `MailroomSectionSettings`
- `settings.labels` attribute -> `settings.mailroom`
- `likely_created` heuristic in reset -> replaced by provenance group check
- Note format without provenance line -> now includes "Created by Mailroom" or "Adopted by Mailroom"

## Open Questions

1. **Provenance group name in check_membership exclusion**
   - What we know: `check_membership()` iterates `self._groups`. Provenance group must be in `_groups` for add/remove operations but excluded from membership checks.
   - What's unclear: Best mechanism -- `infrastructure_groups` set on client, or pass provenance group name through to every `check_membership()` call.
   - Recommendation: Add `infrastructure_groups: set[str]` to CardDAVClient, populated during validation. `check_membership()` skips these. Cleaner than threading group names through call chains.

2. **Provenance group parameter threading**
   - What we know: `upsert_contact()` needs the provenance group name to add new contacts. Currently it only takes `group_name` (the triage group).
   - What's unclear: Whether to add a parameter to `upsert_contact()` or have the caller (`_process_sender`) call `add_to_group()` separately after upsert.
   - Recommendation: Add `provenance_group: str | None = None` parameter to `upsert_contact()`. It keeps the "create contact and add to all groups" logic self-contained. The caller passes `settings.mailroom.provenance_group`.

3. **vobject PRODID field in user-modified detection**
   - What we know: vobject may add `PRODID` automatically when serializing. Need to verify this is in the managed fields set.
   - What's unclear: Exact list of fields vobject auto-adds.
   - Recommendation: Include `prodid` in managed fields. Test with a round-trip to confirm.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (latest, already configured) |
| Config file | `pyproject.toml` (ruff + pytest config) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements -> Test Map

Since phase requirement IDs are TBD, mapping by feature area:

| Feature | Behavior | Test Type | Automated Command | File Exists? |
|---------|----------|-----------|-------------------|-------------|
| Config rename | `labels:` -> `mailroom:` parsed correctly | unit | `pytest tests/test_config.py -x` | Needs update |
| Config rename | Old `labels:` key rejected (no backward compat) | unit | `pytest tests/test_config.py -x` | Needs new test |
| Provenance group validation | Startup fails if provenance group missing | unit | `pytest tests/test_config.py -x` | Needs new test |
| Provenance note (created) | `create_contact()` includes "Created by Mailroom" line | unit | `pytest tests/test_carddav_client.py -x` | Needs update |
| Provenance note (adopted) | `upsert_contact()` existing includes "Adopted by Mailroom" | unit | `pytest tests/test_carddav_client.py -x` | Needs update |
| Provenance group add | `upsert_contact()` with action=created adds to provenance group | unit | `pytest tests/test_carddav_client.py -x` | Needs new test |
| Provenance group skip | `upsert_contact()` with action=existing skips provenance group | unit | `pytest tests/test_carddav_client.py -x` | Needs new test |
| check_membership exclusion | Provenance group not returned by check_membership() | unit | `pytest tests/test_carddav_client.py -x` | Needs new test |
| @MailroomWarning cleanup | Warning labels removed before processing sender | unit | `pytest tests/test_screener_workflow.py -x` | Needs new test |
| @MailroomWarning reapply | Warning reapplied if condition persists after cleanup | unit | `pytest tests/test_screener_workflow.py -x` | Needs new test |
| delete_contact | CardDAV DELETE with If-Match | unit | `pytest tests/test_carddav_client.py -x` | Needs new test |
| User-modified detection | Extra vCard fields detected correctly | unit | `pytest tests/test_resetter.py -x` | Needs new test |
| Reset provenance DELETE | Unmodified provenance contacts deleted | unit | `pytest tests/test_resetter.py -x` | Needs update |
| Reset provenance WARN | Modified provenance contacts get @MailroomWarning on emails | unit | `pytest tests/test_resetter.py -x` | Needs new test |
| Reset adopted cleanup | Non-provenance contacts get note stripped + group removed | unit | `pytest tests/test_resetter.py -x` | Needs update |
| Reset operation order | 7-step order verified | unit | `pytest tests/test_resetter.py -x` | Needs update |
| Setup provisioner | Provenance group in plan + apply | unit | `pytest tests/test_provisioner.py -x` | Needs update |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Update `tests/conftest.py` -- `mock_settings` fixture must produce settings with `mailroom` section instead of `labels`
- [ ] Update `config.yaml.example` -- rename `labels:` to `mailroom:` with new key names
- [ ] No new framework installs needed -- pytest infrastructure is complete

## Sources

### Primary (HIGH confidence)
- Source code analysis: `src/mailroom/clients/carddav.py` -- all CardDAV operations verified
- Source code analysis: `src/mailroom/core/config.py` -- all config patterns verified
- Source code analysis: `src/mailroom/workflows/screener.py` -- all triage pipeline patterns verified
- Source code analysis: `src/mailroom/reset/resetter.py` -- all reset patterns verified
- Source code analysis: `src/mailroom/setup/provisioner.py` -- all setup patterns verified
- CONTEXT.md -- all user decisions verified and incorporated
- RFC 4918 Section 9.6 -- WebDAV DELETE method (standard, well-known)

### Secondary (MEDIUM confidence)
- vobject `PRODID` auto-addition behavior -- based on library experience, needs round-trip verification

### Tertiary (LOW confidence)
None -- all findings are from direct code inspection.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing libraries
- Architecture: HIGH -- patterns directly derived from existing codebase
- Pitfalls: HIGH -- identified through code analysis of actual integration points
- Config rename impact: HIGH -- grep-verified all reference sites

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable -- internal project, no external API changes expected)
