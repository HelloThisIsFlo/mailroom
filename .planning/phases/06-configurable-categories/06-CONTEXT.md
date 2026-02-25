# Phase 6: Configurable Categories - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can define and customize their triage categories through a single structured JSON configuration (`MAILROOM_TRIAGE_CATEGORIES` env var). The service derives all behavior — triage labels, contact groups, required mailboxes — from that mapping. Zero-config deployments get the same 5 default categories as v1.0. Startup validation rejects invalid configs with clear error messages.

</domain>

<decisions>
## Implementation Decisions

### Category JSON shape
- Name-only config: user provides `{ "name": "Receipts" }` and label, group, mailbox are derived
- Derivation rules: label = `@To{NameNoSpaces}` (e.g., "Paper Trail" → @ToPaperTrail), group = `{Name}`, mailbox = `{Name}`
- All derived fields are overridable: `label`, `contact_group`, `destination_mailbox` can each be explicitly set
- Category order in the JSON array has no semantic meaning — no priority implied

### Person type handling
- Person is a regular category with an optional `contact_type` field (default: "company")
- `contact_type` is restricted to known values: "company", "person" — unknown values rejected at startup
- Optional `parent` field declares hierarchy: `{ "name": "Person", "parent": "Imbox", "contact_type": "person" }`
- Children inherit parent's `contact_group` and `destination_mailbox` (can be overridden)
- Shared contact groups are only allowed via parent relationship — flagged otherwise
- Setup script (Phase 7) uses `parent` to create nested Fastmail mailboxes; engine doesn't use hierarchy

### add-inbox semantics
- No separate add-inbox flag — `destination_mailbox` fully controls where emails land
- Imbox sets `destination_mailbox: "Inbox"` to deliver to Inbox; Feed sets `destination_mailbox: "Feed"` to stay out of Inbox
- Any valid Fastmail mailbox name allowed as destination — not restricted to a known set
- Startup validates all destination mailboxes exist on Fastmail (crashes with clear error if missing)
- CONFIG-01 requirement needs update: "add-inbox flag" → "destination mailbox per category"

### Default-vs-custom behavior
- Full replacement: if `MAILROOM_TRIAGE_CATEGORIES` is set, it IS the complete category list — no defaults mixed in
- No env var = built-in defaults matching v1.0 (Imbox, Person, Feed, Paper Trail, Jail)
- Fully custom allowed — no default categories required, just at least one category
- Default config documented in README and shown in validation error messages for reference

### Startup validation
- All errors shown at once (not fail-fast on first error)
- Validates: duplicate category names, missing 'name' field, invalid contact_type values, parent referencing non-existent category, circular parent chains, empty category list
- Destination mailbox existence validated separately (against live Fastmail)

### Claude's Discretion
- Pydantic model design for the category structure
- How defaults are represented in code (frozen list, factory function, etc.)
- Internal data structures for the resolved category mapping
- Error message formatting and wording
- Test structure and organization

</decisions>

<specifics>
## Specific Ideas

- User noted: `contact_type` as a field "puts a possibility of having other types of contacts in the future" — design should be extensible
- The default JSON block in error messages should be copy-pasteable so users can extend it easily
- Parent-child relationship (Person under Imbox) emerged from real Fastmail mailbox hierarchy — not just a config convenience

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-configurable-categories*
*Context gathered: 2026-02-25*
