# Phase 7: Setup Script - Research

**Researched:** 2026-02-26
**Domain:** CLI tooling, JMAP Mailbox/set, CardDAV group creation, Sieve script introspection
**Confidence:** HIGH

## Summary

Phase 7 adds a `mailroom setup` subcommand that provisions Fastmail resources (mailboxes and contact groups) required by the user's configured triage categories, with dry-run safety and sieve rule guidance. The implementation touches four technical domains: (1) CLI framework integration with Click, (2) JMAP `Mailbox/set` for creating mailboxes, (3) CardDAV PUT for creating Apple-style contact groups, and (4) JMAP `SieveScript/get` for read-only sieve introspection.

The project already has robust JMAP and CardDAV clients (`JMAPClient` and `CardDAVClient`) that handle session discovery, authentication, and API calls. The setup script extends these clients with create operations (currently only read/query/update operations exist). The config system (`MailroomSettings`) already computes `required_mailboxes` and `contact_groups` from categories -- the setup script reads these same properties.

**Primary recommendation:** Use Click (already a transitive dependency via the ecosystem, minimal, battle-tested) for CLI with two subcommands (`setup` and `run`). Extend `JMAPClient` with `create_mailbox()` and `CardDAVClient` with `create_group()`. Sieve checking via JMAP `SieveScript/get` if the capability is available, with graceful degradation.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Summary table with indented tree showing mailbox hierarchy (parent `Triage/` with child mailboxes)
- Three resource groups displayed separately: **Mailboxes** (with hierarchy), **Action Labels** (triage labels like "to Feed"), **Contact Groups** (like "Imbox", "Feed")
- Statuses: `+ create` (dry-run), `created` (apply), `FAILED` (apply failure), `exists`
- Live progress during `--apply` -- each resource reported as it's processed
- Summary line at bottom: `N created . N existing` (or `N to create . N existing` for dry-run)
- Inline error reasons for failures (e.g., `403 Forbidden: insufficient permissions`)
- Read-only sieve check: query Fastmail's sieve scripts to detect if routing rules exist
- Check both per-category routing rules AND the screener catch-all rule
- Sieve statuses: `found`, `missing`, `? unknown` (ambiguous/custom rules)
- Copy-paste sieve snippets shown by default for missing rules only
- `--ui-guide` flag available for Fastmail UI-based instructions instead of sieve snippets
- Subcommand: `mailroom setup` (not a standalone script)
- Requires introducing a CLI framework (click or typer -- Claude's discretion)
- `--apply` flag to make changes; dry-run by default (no flag = dry-run)
- Continue on failure: attempt all resources, report successes and failures at the end
- Skip dependent resources when parent fails (e.g., skip child mailboxes if Triage/ parent creation fails) -- mark as `skipped (parent failed)`
- Pre-flight connectivity check on both dry-run and apply (verify JMAP + CardDAV credentials before attempting anything)
- Exit codes: 0 = all good, 1 = at least one failure
- Idempotent re-run retries failed resources (successes skipped as "exists")

### Claude's Discretion
- Click vs Typer for CLI framework
- Whether `python -m mailroom` (no subcommand) runs the service or requires `mailroom run`
- Human test strategy for setup script
- Loading skeleton / progress indicator implementation
- Exact sieve rule pattern matching heuristics

### Deferred Ideas (OUT OF SCOPE)
- Automated sieve rule creation via JMAP Sieve/set -- research feasibility first; if too complex, make this a future phase or todo item
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SETUP-01 | Setup script creates missing triage label mailboxes on Fastmail via JMAP `Mailbox/set` | JMAP Mailbox/set create pattern documented; extend JMAPClient with create_mailbox() |
| SETUP-02 | Setup script creates missing contact groups on Fastmail via CardDAV | CardDAV Apple-style group vCard creation via PUT documented; extend CardDAVClient with create_group() |
| SETUP-03 | Setup script is idempotent -- reports "already exists" for items that are already present | Use existing resolve_mailboxes() and validate_groups() for existence checks before create |
| SETUP-04 | Setup script outputs human-readable sieve rule instructions for email routing | Sieve snippets use `fileinto "INBOX.Folder"` syntax; contact-group-based routing not possible in sieve -- must be per-category folder routing |
| SETUP-05 | Setup script requires `--apply` flag to make changes (dry-run by default) | Click boolean flag `--apply` with default False; exit codes 0/1 |
| SETUP-06 | Setup script reads categories from the same config as the main service | MailroomSettings already exposes required_mailboxes and contact_groups properties |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| click | 8.3.x | CLI framework with subcommands | Battle-tested, zero extra deps (Typer depends on Click), minimal for 2-command CLI |
| httpx | (existing) | HTTP client for JMAP and CardDAV | Already in project deps |
| vobject | (existing) | vCard construction for contact groups | Already in project deps |
| pydantic-settings | (existing) | Config loading from env vars | Already in project deps |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | (existing) | Structured logging | Already in project, use for setup operations too |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Click | Typer 0.24.x | Typer adds type-hint magic but pulls in Click + rich + shellingham as deps. For a 2-command CLI, Click's simplicity wins. Typer is better for large CLIs. |
| Click | argparse (stdlib) | argparse works but subcommand handling is clunkier, no rich help formatting, more boilerplate. |

**Installation:**
```bash
uv add click
```

## Architecture Patterns

### Recommended Project Structure
```
src/mailroom/
  __init__.py
  __main__.py           # Updated: dispatch to CLI
  cli.py                # NEW: Click app with setup + run subcommands
  core/
    config.py           # Existing: MailroomSettings
    logging.py          # Existing
  clients/
    jmap.py             # Extended: add create_mailbox()
    carddav.py          # Extended: add create_group()
  workflows/
    screener.py         # Existing
  setup/                # NEW: setup command implementation
    __init__.py
    provisioner.py      # Orchestrates resource provisioning
    sieve_checker.py    # Sieve script introspection (if capability available)
    reporting.py        # Output formatting (table, summary, sieve snippets)
```

### Pattern 1: Click Subcommand Architecture
**What:** Single Click group with `setup` and `run` subcommands
**When to use:** When adding CLI structure to an existing `__main__.py` service

```python
# src/mailroom/cli.py
import click
import sys

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Mailroom: Email triage automation for Fastmail."""
    if ctx.invoked_subcommand is None:
        # No subcommand = run the service (backward compat)
        ctx.invoke(run)

@cli.command()
def run():
    """Run the Mailroom polling service."""
    from mailroom.__main__ import main
    main()

@cli.command()
@click.option("--apply", is_flag=True, help="Apply changes (default is dry-run)")
@click.option("--ui-guide", is_flag=True, help="Show Fastmail UI instructions instead of sieve snippets")
def setup(apply, ui_guide):
    """Provision Fastmail resources for configured triage categories."""
    from mailroom.setup.provisioner import run_setup
    exit_code = run_setup(apply=apply, ui_guide=ui_guide)
    sys.exit(exit_code)
```

**Backward compatibility:** `python -m mailroom` (no subcommand) invokes `run` via `invoke_without_command=True`. This preserves Dockerfile `CMD ["python", "-m", "mailroom"]` without changes.

### Pattern 2: Provisioner with Resource Plan
**What:** Build a plan of all resources, check existence, then apply
**When to use:** Terraform-style dry-run/apply pattern

```python
# Conceptual pattern for the provisioner
@dataclass
class ResourceAction:
    kind: str           # "mailbox", "label", "contact_group"
    name: str
    status: str         # "exists", "create", "created", "failed", "skipped"
    parent: str | None  # For dependency tracking
    error: str | None   # Inline error message

def plan_resources(settings: MailroomSettings, jmap: JMAPClient, carddav: CardDAVClient) -> list[ResourceAction]:
    """Build resource plan: check what exists, what needs creating."""
    ...

def apply_resources(plan: list[ResourceAction], jmap: JMAPClient, carddav: CardDAVClient) -> list[ResourceAction]:
    """Execute the plan, creating missing resources. Returns updated plan."""
    ...
```

### Pattern 3: JMAP Mailbox/set Create
**What:** Create mailboxes via JMAP Mailbox/set with parent reference
**When to use:** Creating triage label mailboxes and destination mailboxes

```python
# Source: RFC 8621 Mailbox/set
# Add to JMAPClient
def create_mailbox(self, name: str, parent_id: str | None = None) -> str:
    """Create a mailbox and return its server-assigned ID."""
    responses = self.call(
        [["Mailbox/set", {
            "accountId": self.account_id,
            "create": {
                "mb0": {
                    "name": name,
                    "parentId": parent_id,
                    "isSubscribed": True,
                }
            }
        }, "c0"]]
    )
    data = responses[0][1]
    created = data.get("created", {})
    if "mb0" in created:
        return created["mb0"]["id"]
    not_created = data.get("notCreated", {})
    error = not_created.get("mb0", {})
    raise RuntimeError(
        f"Failed to create mailbox '{name}': "
        f"{error.get('type', 'unknown')} - {error.get('description', '')}"
    )
```

### Pattern 4: CardDAV Group Creation
**What:** Create Apple-style contact group via vCard PUT
**When to use:** Creating contact groups like "Imbox", "Feed", etc.

```python
# Source: CardDAV Apple-style groups (X-ADDRESSBOOKSERVER-KIND)
# Add to CardDAVClient
def create_group(self, name: str) -> dict:
    """Create a contact group vCard in the addressbook."""
    addressbook_url = self._require_connection()
    group_uid = str(uuid.uuid4())

    card = vobject.vCard()
    card.add("uid").value = group_uid
    card.add("fn").value = name
    card.add("n").value = vobject.vcard.Name()
    card.add("x-addressbookserver-kind").value = "group"

    href_path = f"{group_uid}.vcf"
    put_url = f"{addressbook_url}{href_path}"

    resp = self._http.put(
        put_url,
        content=card.serialize().encode("utf-8"),
        headers={
            "Content-Type": "text/vcard; charset=utf-8",
            "If-None-Match": "*",
        },
    )
    resp.raise_for_status()

    return {
        "href": f"/{group_uid}.vcf",
        "etag": resp.headers.get("etag", ""),
        "uid": group_uid,
    }
```

### Pattern 5: Sieve Rule Checking (Read-Only)
**What:** Query sieve scripts via JMAP `SieveScript/get` to detect existing rules
**When to use:** Checking if routing rules are already configured

```python
# Source: RFC 9661 SieveScript/get
# The capability "urn:ietf:params:jmap:sieve" must be in the session capabilities.
# If not available, gracefully degrade to "? unknown" status for all sieve checks.

def check_sieve_scripts(self) -> str | None:
    """Fetch sieve script content if capability is available."""
    # 1. Check session capabilities for "urn:ietf:params:jmap:sieve"
    # 2. If available, call SieveScript/get to fetch active script
    # 3. Parse script text for fileinto rules matching category mailboxes
    # 4. If not available, return None (graceful degradation)
```

**Important sieve finding:** Fastmail's sieve cannot route by contact group membership. Sieve rules route by sender address or domain. The sieve snippets for Mailroom should be simple `fileinto` rules that route to destination mailboxes based on the Fastmail UI rule system (which uses the `jmapquery` extension internally).

### Pattern 6: Sieve Snippet Generation
**What:** Generate copy-paste sieve code for email routing
**When to use:** Showing users what sieve rules to create for each category

```sieve
# Mailroom routing rules for category: Feed
# Route emails from "Feed" contact group members to Triage/Feed
# Note: Fastmail sieve cannot filter by contact group directly.
# Use Fastmail UI: Settings > Filters & Rules > Add Rule:
#   Condition: "Sender is in contact group Feed"
#   Action: "Move to folder Feed"

# OR use the Fastmail sieve approach with jmapquery:
# (This is what Fastmail's UI generates internally)
```

**Critical finding:** The CONTEXT.md mentions sieve snippets, but Fastmail sieve has no `fromContactGroup` test. The routing must be configured through:
1. **Fastmail UI rules** (Settings > Filters & Rules) -- which use `jmapquery` internally and CAN reference contact groups
2. **Manual sieve code** -- which can only match by `address :is "From"` for specific senders

**Recommendation for sieve guidance:** Focus on Fastmail UI-based instructions as the primary path (the `--ui-guide` flag output). The "default" sieve snippet approach should show a conceptual template since actual sieve cannot reference contact groups. The UI instructions are more practical.

### Anti-Patterns to Avoid
- **Creating all mailboxes in parallel without ordering:** Parent mailboxes must be created before children. The Triage/ parent must exist before Triage/Feed, Triage/Jail, etc.
- **Failing fast on first error:** The user expects all resources to be attempted with a summary at the end. Use continue-on-failure with dependency tracking.
- **Re-inventing existence checks:** The existing `resolve_mailboxes()` and `validate_groups()` already check what exists. Catch their `ValueError` to detect missing resources rather than writing new check logic.
- **Modifying `__main__.py` extensively:** Keep the existing `main()` function intact. The CLI layer calls it -- don't restructure the startup sequence.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLI argument parsing | Custom argparse wrapper | Click `@group` + `@command` | Subcommands, help text, flags all handled |
| Mailbox existence check | New JMAP query | Existing `JMAPClient.resolve_mailboxes()` | Already handles Inbox role resolution, name collisions |
| Contact group existence check | New CardDAV query | Existing `CardDAVClient.validate_groups()` | Already fetches all vCards, filters by `X-ADDRESSBOOKSERVER-KIND` |
| vCard serialization | Manual string building | `vobject.vCard()` builder | Handles escaping, line folding, vCard format |
| Config loading | New config parser | `MailroomSettings()` constructor | Already reads `MAILROOM_TRIAGE_CATEGORIES` and derives all properties |
| Colored terminal output | ANSI escape code strings | Unicode status symbols (no color dep) | Keep it simple -- no rich/colorama dependency needed |

**Key insight:** The heavy lifting (JMAP session management, CardDAV discovery, config parsing/validation) is already done. The setup script is primarily orchestration and reporting.

## Common Pitfalls

### Pitfall 1: Mailbox Parent-Child Ordering
**What goes wrong:** Creating `Triage/Feed` before `Triage/` parent exists causes a JMAP error.
**Why it happens:** JMAP `Mailbox/set` requires `parentId` to reference an existing mailbox.
**How to avoid:** Create parent mailboxes first. Use a two-phase approach: (1) create parents, (2) create children with parent IDs. JMAP does support batch creation with client-side references (`#id`), but sequential is simpler and more debuggable.
**Warning signs:** `notCreated` response with `parentNotFound` error type.

### Pitfall 2: Mailbox Name vs Mailbox Path Confusion
**What goes wrong:** Fastmail stores mailboxes with a flat `name` + `parentId` structure, not path strings. The display path "Triage/Feed" means a mailbox named "Feed" with parentId pointing to a mailbox named "Triage".
**Why it happens:** IMAP-style path thinking leaks into JMAP code.
**How to avoid:** Always work with (name, parentId) pairs. The `resolve_mailboxes()` method already handles this correctly.
**Warning signs:** Creating a mailbox literally named "Triage/Feed" instead of "Feed" under "Triage".

### Pitfall 3: Sieve Script Content Access
**What goes wrong:** Assuming `SieveScript/get` returns script text directly. It returns a `blobId` reference.
**Why it happens:** RFC 9661 stores script content as blobs, not inline text.
**How to avoid:** After getting the `blobId`, fetch the blob content via the JMAP blob download URL. The session object includes a `downloadUrl` template.
**Warning signs:** Getting a blob ID instead of script text and not knowing how to download it.

### Pitfall 4: Sieve Capability Not Available
**What goes wrong:** Calling `SieveScript/get` when Fastmail doesn't expose `urn:ietf:params:jmap:sieve` capability, causing a JMAP error.
**Why it happens:** While Fastmail's co-founder authored RFC 9661, Fastmail's public API docs don't explicitly list sieve as a supported capability. It may or may not be exposed.
**How to avoid:** Check session capabilities first. If `urn:ietf:params:jmap:sieve` is not in capabilities, gracefully degrade to `? unknown` status for all sieve checks and show sieve snippets unconditionally.
**Warning signs:** `unknownMethod` or `unknownCapability` JMAP error response.

### Pitfall 5: CardDAV Group UID Format
**What goes wrong:** Creating a group vCard without proper `X-ADDRESSBOOKSERVER-KIND:group` marker means `validate_groups()` won't find it.
**Why it happens:** Forgetting the Apple-style group marker, or using wrong capitalization.
**How to avoid:** Follow the exact pattern from existing `validate_groups()`: the code checks `x-addressbookserver-kind` contents for value `"group"` (lowercase comparison). Include the marker in `create_group()`.
**Warning signs:** Group is created on server but `validate_groups()` reports it missing.

### Pitfall 6: Console Script Entry Point
**What goes wrong:** Adding `[project.scripts]` entry to pyproject.toml but Docker still uses `python -m mailroom`.
**Why it happens:** Need to update both the entry point AND ensure backward compatibility.
**How to avoid:** Use Click's `invoke_without_command=True` so `python -m mailroom` (no subcommand) runs the service. Add `[project.scripts] mailroom = "mailroom.cli:cli"` for local development. Dockerfile `CMD` stays unchanged.
**Warning signs:** Docker containers failing because `mailroom` binary doesn't exist in PATH.

## Code Examples

### JMAP Mailbox/set Create (RFC 8621)
```python
# Source: RFC 8621 Section 2 - Mailbox/set
# Create a top-level mailbox
responses = jmap.call([
    ["Mailbox/set", {
        "accountId": jmap.account_id,
        "create": {
            "new0": {
                "name": "Triage",
                "parentId": None,
                "isSubscribed": True,
            }
        }
    }, "c0"]
])

# Response structure:
# {"created": {"new0": {"id": "Ma1234..."}}, "notCreated": {}}
```

### JMAP Batch Create with Parent Reference
```python
# Source: RFC 8621 - client-side ID references
# Create parent and child in one call (parent must be first in create map)
responses = jmap.call([
    ["Mailbox/set", {
        "accountId": jmap.account_id,
        "create": {
            "parent": {
                "name": "Triage",
                "parentId": None,
                "isSubscribed": True,
            },
            "child": {
                "name": "Feed",
                "parentId": "#parent",  # References creation ID
                "isSubscribed": True,
            }
        }
    }, "c0"]
])
```

### CardDAV Group vCard Creation
```python
# Source: Apple-style contact group format
# (Same pattern as existing create_contact in carddav.py)
card = vobject.vCard()
card.add("uid").value = str(uuid.uuid4())
card.add("fn").value = "Feed"
card.add("n").value = vobject.vcard.Name()
card.add("x-addressbookserver-kind").value = "group"
# Result: vCard with X-ADDRESSBOOKSERVER-KIND:group
# PUT to addressbook URL with If-None-Match: *
```

### Click Subcommand with Exit Code
```python
# Source: Click 8.3.x documentation
@cli.command()
@click.option("--apply", is_flag=True, default=False)
def setup(apply: bool) -> None:
    """Provision Fastmail resources."""
    exit_code = run_setup(apply=apply)
    sys.exit(exit_code)
```

### SieveScript/get via JMAP (RFC 9661)
```python
# Source: RFC 9661 - SieveScript/get
# Check if capability is available first
session = jmap.session  # Need to expose session data
if "urn:ietf:params:jmap:sieve" in session.get("capabilities", {}):
    responses = jmap.call([
        ["SieveScript/get", {
            "accountId": jmap.account_id,
            "ids": None,  # Fetch all scripts
        }, "s0"]
    ])
    scripts = responses[0][1]["list"]
    # Each script has: id, name, blobId, isActive
    # To get content: download blob via session downloadUrl template
```

### Fastmail Sieve Snippet Template
```sieve
# Mailroom routing rule for: Feed
# When a sender is in the "Feed" contact group, route to Feed mailbox
#
# IMPORTANT: This rule should be created via Fastmail UI, not raw sieve.
# Go to: Settings > Filters & Rules > Add Rule
#   If: sender "is in contact group" Feed
#   Then: Move to folder "Feed"
#
# Manual sieve equivalent (per-sender, less practical):
# require ["fileinto"];
# if address :is "From" "sender@example.com" {
#   fileinto "INBOX.Feed";
# }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sieve for all filtering | Fastmail UI rules + jmapquery | 2023+ | UI rules can reference contact groups; raw sieve cannot |
| JMAP Sieve draft spec | RFC 9661 published | Oct 2024 | SieveScript/get,set,query,validate now standardized |
| Manual mailbox creation | JMAP Mailbox/set | RFC 8621 (2019) | Programmatic mailbox provisioning is standard |
| Custom CLI argparse | Click/Typer ecosystem | 2020+ | Click 8.x is the standard for Python CLIs |

**Deprecated/outdated:**
- The project's REQUIREMENTS.md says "Fastmail has no API for filter rules" -- this is partially outdated. RFC 9661 provides JMAP `SieveScript/get` for reading sieve scripts. Writing is possible via `SieveScript/set` but is risky (could break existing rules) and is correctly deferred.

## Critical Design Decisions

### CLI Framework: Click (recommended)
**Rationale:** Click 8.3.x is the right choice over Typer for this project:
1. **Minimal dependency:** Click is a single package. Typer pulls in Click + rich + shellingham.
2. **Project scale:** Two subcommands (`setup` and `run`) don't benefit from Typer's type-hint magic.
3. **No Rich dependency needed:** The output format (unicode symbols, plain text tables) doesn't need Rich.
4. **Ecosystem fit:** The project uses pydantic, structlog, httpx -- all mature, no-frills libraries. Click fits this aesthetic.

### Backward Compatibility: invoke_without_command
**Rationale:** `python -m mailroom` must continue to run the service (Docker CMD). Click's `invoke_without_command=True` makes no-subcommand == `run`. This means:
- `python -m mailroom` -> runs service (backward compat)
- `python -m mailroom run` -> runs service (explicit)
- `python -m mailroom setup` -> dry-run setup
- `python -m mailroom setup --apply` -> apply setup

### Sieve Checking: Capability-Gated with Graceful Degradation
**Rationale:** We cannot know at research time whether Fastmail exposes `urn:ietf:params:jmap:sieve`. The implementation must:
1. Check session capabilities at connect time
2. If available: fetch active sieve script, parse for `fileinto` rules matching category mailboxes
3. If not available: report all sieve checks as `? unknown (sieve API not available)`
4. Always show sieve guidance snippets (UI instructions or sieve code) regardless of check status

### Sieve Snippets: UI Instructions as Primary Path
**Rationale:** Fastmail sieve cannot filter by contact group membership. The `jmapquery` extension used internally by Fastmail UI rules CAN reference contact groups, but this is only accessible through Fastmail's Settings UI. Therefore:
- **Default output** (`mailroom setup`): Show per-category Fastmail UI rule instructions (since this is what users will actually do)
- **`--ui-guide` flag**: Already planned for UI instructions -- make this the default behavior with sieve code shown as an alternative/reference
- **Sieve snippets**: Show as reference material noting they require per-sender address matching (less practical)

**Wait -- re-reading the CONTEXT.md:** The user decided "Copy-paste sieve snippets shown by default for missing rules only" and `--ui-guide` for Fastmail UI instructions. So the default IS sieve snippets, with UI guide as the alternative. However, since sieve can't reference contact groups, the "sieve snippets" should actually be the Fastmail UI `jmapquery`-style rule syntax that Fastmail generates when you create a rule via Settings. This is a practical concern the planner needs to address: what exactly does a "sieve snippet" look like when contact-group-based routing is only possible via the UI?

**Practical resolution:** The sieve snippets should be conceptual templates showing the Fastmail sieve code that gets generated when you create a UI rule. These rules use `jmapquery` with JSON conditions. The snippet can say:
```sieve
require ["vnd.cyrus.jmapquery", "fileinto"];
if jmapquery text:
{"fromContactGroupId":"<GROUP_ID>"}
.
{
  fileinto "INBOX.Feed";
}
```
Whether `fromContactGroupId` exists as a jmapquery key is unverified (LOW confidence), but this is the pattern Fastmail's UI rules generate. If this doesn't work as raw sieve, the snippet should include a note directing users to the UI. The `--ui-guide` flag provides step-by-step UI instructions as the safe fallback.

### Resource Categorization for Output
**Rationale:** The CONTEXT.md specifies three display groups. Mapping to the config system:
1. **Mailboxes** (destination mailboxes with hierarchy): `settings.required_mailboxes` filtered to only destination-type mailboxes (Feed, Paper Trail, Jail, Inbox) -- NOT triage labels, NOT system mailboxes like Screener
2. **Action Labels** (triage label mailboxes): All items from `settings.triage_labels` (e.g., @ToFeed, @ToJail) plus `@MailroomError` and optionally `@MailroomWarning`
3. **Contact Groups**: `settings.contact_groups` (e.g., Imbox, Feed, Paper Trail, Jail)

Note: "Mailboxes" and "Action Labels" are both JMAP mailboxes under the hood. The distinction is presentation-only. The setup script needs to know which mailboxes are "destination" vs "triage label" for correct categorization in the output.

### Human Test Strategy
**Rationale:** The project uses `human-tests/` for real Fastmail integration tests. The setup script should have:
1. `test_14_setup_dry_run.py` -- runs `mailroom setup` (dry-run), verifies output contains expected resources
2. `test_15_setup_apply.py` -- runs `mailroom setup --apply`, verifies resources created, runs again to verify idempotency
3. These tests are destructive (create real resources) so should include cleanup logic or use test-specific resource names

## Open Questions

1. **Does Fastmail expose `urn:ietf:params:jmap:sieve` capability?**
   - What we know: RFC 9661 is authored by Fastmail's co-founder. The capability is standardized.
   - What's unclear: Whether it's enabled in Fastmail's production JMAP session.
   - Recommendation: Implement capability check at runtime. Gracefully degrade if not available. Can be verified with a quick `curl` against the session endpoint during implementation.

2. **What does Fastmail's jmapquery filter look like for contact group conditions?**
   - What we know: Fastmail UI rules generate `jmapquery` sieve blocks internally. The rules UI supports "sender in contact group" conditions.
   - What's unclear: The exact JSON structure of the jmapquery filter for contact groups (e.g., `fromContactGroupId` vs `inContactGroup` vs something else).
   - Recommendation: LOW confidence on exact jmapquery JSON format. The sieve snippets should note this as "generated by Fastmail UI" and direct users to create rules via the UI for reliability.

3. **Mailbox hierarchy for triage labels: flat or nested?**
   - What we know: CONTEXT.md mentions "parent `Triage/` with child mailboxes" in the output display.
   - What's unclear: Whether triage labels (like `@ToFeed`) are actually nested under a parent mailbox, or just displayed with a tree-like indent.
   - Recommendation: Looking at existing code, `required_mailboxes` returns flat names like `@ToFeed`, `Feed`, `Inbox`. There is no `Triage/` parent in the current config. The "hierarchy" in the output may refer to the visual grouping, not actual Fastmail nesting. Check with user if unclear -- but for now, create mailboxes as flat (top-level) per the existing config system.

## Sources

### Primary (HIGH confidence)
- [RFC 8621 - JMAP for Mail](https://datatracker.ietf.org/doc/html/rfc8621) - Mailbox/set create specification
- [RFC 9661 - JMAP for Sieve Scripts](https://datatracker.ietf.org/doc/html/rfc9661) - SieveScript/get,set,query,validate
- [Click 8.3.x Documentation](https://click.palletsprojects.com/en/stable/) - CLI framework API
- [Fastmail Sieve Extensions](https://www.fastmail.help/hc/en-us/articles/1500000280481-Using-Sieve-scripts-in-Fastmail) - Supported sieve extensions list
- Project source: `src/mailroom/clients/jmap.py` - Existing JMAP client patterns
- Project source: `src/mailroom/clients/carddav.py` - Existing CardDAV client patterns with Apple-style groups
- Project source: `src/mailroom/core/config.py` - MailroomSettings with required_mailboxes and contact_groups

### Secondary (MEDIUM confidence)
- [Fastmail API Documentation](https://www.fastmail.com/dev/) - Documented JMAP scopes (mail, submission, vacationresponse)
- [Fastmail Sieve Examples](https://www.fastmail.help/hc/en-us/articles/360058753794-Sieve-examples) - Sieve `fileinto` syntax for Fastmail
- [Apple-style CardDAV Groups](https://github.com/mstilkerich/rcmcarddav/blob/master/doc/GROUPS.md) - X-ADDRESSBOOKSERVER-KIND group format

### Tertiary (LOW confidence)
- Fastmail jmapquery contact group filter syntax - No documentation found. The exact JSON structure for contact-group-based jmapquery filters is unverified. Only inferred from Fastmail UI rule behavior.
- Fastmail `urn:ietf:params:jmap:sieve` capability availability - Not listed in Fastmail's public API docs. Must be verified at runtime.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Click is well-documented, project deps are known
- Architecture: HIGH - Extends existing client patterns, config system is well-understood
- JMAP Mailbox/set: HIGH - RFC 8621 is the standard, Mailbox/set create is straightforward
- CardDAV group creation: HIGH - Same pattern as existing create_contact, just with group marker
- Sieve introspection: MEDIUM - RFC 9661 is clear, but Fastmail capability availability unknown
- Sieve snippet content: LOW - Contact-group-based sieve routing not possible; jmapquery syntax unverified
- CLI backward compat: HIGH - Click's invoke_without_command pattern is well-documented

**Research date:** 2026-02-26
**Valid until:** 2026-03-26 (stable domain -- JMAP and CardDAV specs don't change frequently)
