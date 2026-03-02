# Phase 11: Config Layer - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Operators can configure inbox visibility independently of destination mailbox, and child categories resolve as fully independent categories that additively carry parent labels. This phase changes the config model, resolution logic, validation, sieve guidance, and setup CLI. It does NOT change label scanning (Phase 12) or re-triage (Phase 13).

</domain>

<decisions>
## Implementation Decisions

### Default categories
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

### Child independence (CFG-03)
- Child categories derive ALL fields from their own name: label, contact_group, destination_mailbox
- No field inheritance from parent whatsoever
- Parent relationship only means: additive contact groups + additive mailbox filing

### Additive contact groups
- When a sender is triaged to a child category, they are added to the child's contact group AND all ancestor contact groups (full chain walk)
- This enables simple 1:1 sieve rules: each contact group maps to exactly one mailbox
- Example: triaging to Person adds sender to Person group AND Imbox group

### Additive mailbox filing
- When filing/sweeping emails, apply the child's destination mailbox AND all ancestor destination mailboxes
- In Fastmail, mailboxes are labels — adding multiple mailbox IDs makes the email appear in all those folders
- Full chain walk: Grandparent → Parent → Child means filing adds Child + Parent + Grandparent mailbox labels
- Example: triaging to Billboard adds Billboard + Paper Trail mailbox labels

### add_to_inbox semantics (CFG-01)
- Default: `false` (opt-in to Inbox visibility)
- Per-category flag, NEVER inherited through parent chain
- Any category (root or child) can set it independently
- Screener-only: only adds Inbox label to emails that are in Screener at triage time
- Re-triage does NOT re-add Inbox to existing emails (captured in RTRI-06 for Phase 13)
- If Imbox has `add_to_inbox: true` but Person does not, triaging to Person does NOT add Inbox — even though additive filing puts emails in Imbox mailbox too

### destination_mailbox: Inbox validation (CFG-02)
- `destination_mailbox: Inbox` is rejected at startup with helpful error
- Error message: "destination_mailbox: Inbox is not allowed. Use add_to_inbox: true instead to make emails appear in Inbox."

### Sieve guidance (CFG-08)
- Show ALL categories (root AND child), grouped by parent for readability
- Syntax-highlighted style: comments in gray/dim, category names colored, mailbox names colored, sieve keywords colored
- Each rule has: condition (sender in contact group) + actions
- Standard category (no add_to_inbox) — 3 actions:
  1. Add label: `{destination_mailbox}`
  2. Archive (remove Inbox label)
  3. Continue to apply other rules
- Category with `add_to_inbox: true` — 2 actions:
  1. Add label: `{destination_mailbox}`
  2. Continue to apply other rules (NO archive — email stays in Inbox)
- "Continue to apply other rules" is critical: without it, additive labels from parent/child rules won't fire
- Prominent note about this at the top of guidance output

### Setup CLI (CFG-07)
- Provisions separate mailbox and contact group for EACH category (root and child)
- Imbox gets its own `Imbox` mailbox (no longer routing to Inbox)

### config.yaml.example
- Update to show new defaults with `add_to_inbox`, Billboard, and Truck

### Already-grouped check
- Will be deprecated in this milestone (replaced by re-triage in Phase 13)
- Phase 11 does not need to modify the already-grouped logic — it will be removed/replaced later

### Claude's Discretion
- Exact validation error message wording (beyond CFG-02 which is specified)
- Color palette for sieve guidance syntax highlighting (extend existing cyan-based scheme)
- Internal implementation of parent chain walking (recursive vs iterative)
- Test structure and organization

</decisions>

<specifics>
## Specific Ideas

- Sieve guidance colors: "the part about the sieve rule is really hard to read, more colors would be great" — comments in gray, keywords in distinct colors, syntax-highlighted feel
- Fastmail UI rule setup should be crystal clear: operators need to know exactly which checkboxes to enable per rule type
- "Continue to apply other rules" must be called out prominently — this is the one operators are most likely to miss

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TriageCategory` model (config.py:21): needs `add_to_inbox: bool = False` field added
- `ResolvedCategory` dataclass (config.py:46): needs `add_to_inbox: bool` field added
- `_validate_categories()` (config.py:95): extend with CFG-02 validation (reject destination_mailbox=Inbox)
- `resolve_categories()` (config.py:184): remove parent inheritance of contact_group and destination_mailbox
- `_default_categories()` (config.py:78): update with new defaults (add_to_inbox, Billboard, Truck)
- `_highlight_folder()` (sieve_guidance.py:19): extend with new color scheme
- `generate_sieve_guidance()` (sieve_guidance.py:26): remove `cat.parent is None` filter, add child categories
- `colors.py` (setup/colors.py): extend with additional ANSI colors for syntax highlighting

### Established Patterns
- Two-pass resolution: first derive fields, then apply relationships — pattern stays but second pass changes (no field inheritance, only record parent chain)
- Validation collects all errors (not fail-fast) — extend with CFG-02 check
- `_get_destination_mailbox_ids()` (screener.py:353): currently returns single ID — needs to return additive chain of IDs
- Config shorthand: `"- Feed"` string becomes `{"name": "Feed"}` — pattern unchanged

### Integration Points
- `ScreenerWorkflow._file_email()` (screener.py:338): uses `_get_destination_mailbox_ids()` — needs additive chain
- `ScreenerWorkflow._process_sender()` (screener.py): contact upsert needs additive group membership
- `plan_resources()` (provisioner.py:17): already iterates all resolved categories — should work with independent children
- `required_mailboxes` property (config.py:386): already collects from all categories — should work
- `contact_groups` property (config.py:401): already collects from all categories — should work
- `config.yaml.example`: needs update with new defaults

</code_context>

<deferred>
## Deferred Ideas

- Investigate whether contact_group should always equal destination_mailbox (1:1 mapping) — sieve routes by group, so different group+mailbox may not make sense. Capture as future investigation.
- Already-grouped check removal — happens in Phase 13 with re-triage support

</deferred>

---

*Phase: 11-config-layer*
*Context gathered: 2026-03-02*
