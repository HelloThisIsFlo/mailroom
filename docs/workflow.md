# Triage Workflow

Mailroom is an automated email triage service for Fastmail. You apply a label to one email from a sender, and Mailroom takes care of the rest: it creates or updates the sender's contact, files all their emails into the right mailbox, and ensures future emails are auto-routed by Fastmail's sieve rules.

This document explains how the triage system works end to end.

---

## Core Concepts

### Categories

A **category** is a bucket for organizing senders. Each category has:

| Field | Description | Example |
|-------|-------------|---------|
| **name** | The category identifier | `Imbox`, `Feed`, `Person` |
| **label** | Derived as `@To{Name}` -- the action label users apply to triage | `@ToImbox`, `@ToFeed` |
| **contact_group** | Derived from name -- senders triaged here are added to this CardDAV group | `Imbox`, `Feed` |
| **destination_mailbox** | Derived from name -- emails from these senders are filed here | `Imbox`, `Feed` |
| **contact_type** | `company` (default) or `person` -- determines vCard format | `company` |
| **parent** | Optional reference to another category -- establishes hierarchy | `Imbox` |
| **add_to_inbox** | Whether filed emails also appear in Inbox (default: `false`) | `true` |

All fields except `name` are derived automatically. You only need to set fields explicitly when you want non-default behavior. See [config.md](config.md) for configuration details.

### Child Categories Are Independent

A child category (one with `parent` set) is **fully independent**:

- It has its own label, contact group, and destination mailbox -- all derived from its own name
- It does **not** inherit contact_group, destination_mailbox, or any other field from its parent
- The parent relationship only affects two things:
  1. **Additive contact groups** -- the sender is added to the child's group AND all ancestor groups
  2. **Additive mailbox filing** -- emails are filed to the child's destination AND all ancestor destinations

This additive behavior is what makes sieve rules simple: each contact group maps to exactly one mailbox, and a sender in multiple groups (child + parent) gets multiple labels applied naturally.

### add_to_inbox Flag

The `add_to_inbox` flag controls whether emails also appear in the Inbox:

- **Per-category only** -- it is never inherited through the parent chain
- **Screener-only** -- only applies to emails that are currently in the Screener mailbox at triage time
- If a parent has `add_to_inbox: true` but its child does not, emails triaged to the child do NOT get Inbox visibility (even though additive filing puts them in the parent's mailbox too)

**Why Screener-only?** The Screener is the sandbox for incoming mail. When a sender is first triaged, their Screener emails are swept to the appropriate destination. The `add_to_inbox` flag determines whether those fresh emails should also appear in Inbox. But when a contact is re-triaged (moved between categories), their existing emails should NOT be re-added to Inbox -- they are not new.

### destination_mailbox: Inbox Is Banned

Setting `destination_mailbox: Inbox` is a validation error. Use `add_to_inbox: true` instead.

This enforces separation of concerns: the destination mailbox is where emails are filed, and Inbox visibility is a separate, independent flag. Without this rule, it would be ambiguous whether Inbox filing should propagate through the parent chain.

---

## Default Categories

The default configuration ships 7 categories organized into a parent-child hierarchy:

```yaml
triage:
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

What this produces:

| Category | Label | Contact Group | Destination | Parent | add_to_inbox |
|----------|-------|---------------|-------------|--------|--------------|
| Imbox | @ToImbox | Imbox | Imbox | -- | true |
| Feed | @ToFeed | Feed | Feed | -- | false |
| Paper Trail | @ToPaperTrail | Paper Trail | Paper Trail | -- | false |
| Jail | @ToJail | Jail | Jail | -- | false |
| Person | @ToPerson | Person | Person | Imbox | false |
| Billboard | @ToBillboard | Billboard | Billboard | Paper Trail | false |
| Truck | @ToTruck | Truck | Truck | Paper Trail | false |

Notice that Person has its own contact group (`Person`) and destination mailbox (`Person`) -- it does not inherit `Imbox` for either. The parent relationship means that when you triage someone to Person, they are added to both the `Person` and `Imbox` contact groups, and their emails appear in both the `Person` and `Imbox` mailboxes.

---

## Triage Walkthrough

### Triaging a sender to Person (child of Imbox)

1. **User applies action label** -- Add `@ToPerson` to an email from `sender@example.com`
2. **Mailroom detects the label** -- Label scanning finds the labeled email across all triage label mailboxes
3. **Contact upserted to additive groups** -- Sender is added to:
   - `Person` contact group (the triaged category)
   - `Imbox` contact group (the parent, walking up the full chain)
4. **Emails swept with additive filing** -- All emails from this sender currently in Screener are filed to:
   - `Person` mailbox (child's destination)
   - `Imbox` mailbox (parent's destination)
   - Since `Person` has `add_to_inbox: false` (default) -- **no Inbox label is added**. Only if Person itself had `add_to_inbox: true` would Inbox be added; the parent's flag is never inherited.
5. **Action label removed** -- `@ToPerson` is removed from the email (last step, for retry safety)

### Triaging a sender to Imbox (root category with add_to_inbox)

1. **User applies** `@ToImbox` to an email
2. **Contact upserted** to `Imbox` contact group
3. **Emails swept** from Screener to:
   - `Imbox` mailbox (destination)
   - `Inbox` (because `add_to_inbox: true` AND emails are from Screener)
4. **Action label removed**

### Triaging a sender to Billboard (child of Paper Trail)

1. **User applies** `@ToBillboard`
2. **Contact upserted** to:
   - `Billboard` contact group
   - `Paper Trail` contact group (parent)
3. **Emails swept** from Screener to:
   - `Billboard` mailbox
   - `Paper Trail` mailbox
   - No Inbox (neither Billboard nor Paper Trail has `add_to_inbox`)
4. **Action label removed**

### Deep Nesting Example

If categories were configured as:

```yaml
- name: Grandparent
  add_to_inbox: true
- name: Parent
  parent: Grandparent
- name: Child
  parent: Parent
```

Triaging to **Child**:
- **Contact groups:** Child + Parent + Grandparent (full chain)
- **Mailbox labels:** Child + Parent + Grandparent
- **Inbox:** NOT added -- Grandparent has `add_to_inbox` but Child does not, and the flag is per-category, never inherited

Triaging directly to **Grandparent**:
- **Contact groups:** Grandparent only
- **Mailbox labels:** Grandparent + Inbox (has `add_to_inbox: true`)

---

## Sieve Rules

Fastmail uses sieve rules to auto-route future incoming email. With additive contact groups, each sieve rule is simple -- one contact group maps to one mailbox:

```
Person     -> sender in "Person" group     -> file to "Person" mailbox
Imbox      -> sender in "Imbox" group      -> file to "Imbox" mailbox
Billboard  -> sender in "Billboard" group  -> file to "Billboard" mailbox
Paper Trail -> sender in "Paper Trail" group -> file to "Paper Trail" mailbox
Feed       -> sender in "Feed" group       -> file to "Feed" mailbox
Jail       -> sender in "Jail" group       -> file to "Jail" mailbox
Truck      -> sender in "Truck" group      -> file to "Truck" mailbox
...
Screener catch-all -> all other mail -> file to "Screener"
```

The additive filing happens naturally: a Person sender is in both Person and Imbox groups, so both rules fire, and the email gets both mailbox labels. In Fastmail, mailboxes are labels -- the email appears in both folders.

### Sieve Rule Setup in Fastmail

Create rules in **Fastmail > Settings > Filters & Rules**. Each category needs a rule with specific actions depending on whether it uses `add_to_inbox`.

**Standard category (no `add_to_inbox`)** -- 3 actions:

1. Add label: `{destination_mailbox}`
2. Archive (removes Inbox label)
3. Continue to apply other rules

**Category with `add_to_inbox: true`** -- 2 actions:

1. Add label: `{destination_mailbox}`
2. Continue to apply other rules (NO archive -- email stays in Inbox)

**IMPORTANT: "Continue to apply other rules" must be enabled on ALL category rules.** Without it, additive labels from parent/child rules will not fire. This is the most common setup mistake.

The Screener catch-all rule goes last and files everything unmatched to the Screener mailbox.

---

## Re-triage

When a sender is re-triaged (moved from one category to another), Mailroom detects the existing contact and handles the transition:

1. **Contact moved to new additive groups** -- Added to the new child + parent groups, removed from old groups. Uses a chain diff: groups shared between old and new chains are left untouched, new-only groups are added first, then old-only groups are removed (safe partial-failure order).
2. **All emails re-filed** -- Fetches ALL emails from this sender (not just Screener), strips old managed labels, and applies the new additive mailbox labels.
3. **add_to_inbox NOT applied on re-triage** -- Only Screener emails get Inbox during initial triage. Re-triage does not add Inbox because these emails are not new.
4. **Triage history captured** -- The contact note records the move with a dated entry.

### Sweep Differences: Initial Triage vs Re-triage

| Aspect | Initial Triage | Re-triage |
|--------|---------------|-----------|
| Emails swept | Screener emails only | ALL emails from sender |
| Labels applied | New additive chain | New additive chain |
| Labels removed | Screener | All managed labels + Screener |
| Inbox added | If `add_to_inbox: true` on triaged category | Never |
| Contact groups | Add to full chain | Chain diff (add new, remove old, keep shared) |

---

## Contact Provenance

Mailroom tracks which contacts it creates versus which it adopts (pre-existing contacts triaged by the user):

- **Created contacts** are added to a provenance contact group (default: `Mailroom`). These are contacts Mailroom created from scratch during triage.
- **Adopted contacts** are pre-existing contacts that Mailroom found and added to a triage group. They are NOT added to the provenance group.
- **Triage history** is recorded in the contact's note field:
  - New triage: `Triaged to {group} on {date}`
  - Re-triage: `Re-triaged to {group} on {date}`

The provenance distinction matters for the reset command: created contacts can be safely deleted, while adopted contacts are only cleaned of Mailroom metadata.

---

## Reset CLI

The `mailroom reset` command undoes all Mailroom changes to restore a clean state. It operates in two modes:

- `mailroom reset` -- Dry-run mode. Shows what would be changed without making modifications.
- `mailroom reset --apply` -- Apply mode. Executes the cleanup after a confirmation prompt.

### Reset Operation Order (7 steps)

1. **Move emails to Screener** -- Adds Screener label, then removes managed destination labels from emails (Feed, Imbox, etc.)
2. **Clean system labels** -- Removes `@MailroomWarning` and `@MailroomError` from all emails
3. **Empty contact groups** -- Removes all contacts from category groups (Imbox, Feed, Person, etc.)
4. **Warn about modified contacts** -- Applies `@MailroomWarning` to emails from created contacts that the user has modified
5. **Provenance cleanup** -- Removes warned contacts from the provenance group
6. **Strip Mailroom notes** -- Removes Mailroom triage history from contact notes (for warned + adopted contacts only; contacts about to be deleted are skipped)
7. **Delete created contacts** -- Permanently deletes unmodified contacts that Mailroom created

### Provenance-Aware Behavior

| Contact Type | Action |
|-------------|--------|
| Created, unmodified | Deleted (step 7) |
| Created, user-modified | Warned via @MailroomWarning, note stripped, provenance removed |
| Adopted (pre-existing) | Note stripped only |

"User-modified" means the contact has fields beyond what Mailroom manages (e.g., phone numbers, addresses, additional notes).

---

## Validation Rules

At startup, the configuration validator checks:

1. **At least one category** is required
2. **No duplicate names** across categories
3. **All parent references** point to existing categories
4. **No circular parent chains** (including self-reference)
5. **No duplicate labels** after derivation (e.g., two categories resolving to `@ToFeed`)
6. **No `destination_mailbox: Inbox`** -- use `add_to_inbox: true` instead
7. **No shared contact groups** unless the categories are related via parent chain

Validation collects all errors before reporting, so you see every problem at once rather than fixing them one at a time.

---

## Further Reading

- [Configuration Reference](config.md) -- YAML config file structure, credentials, and all settings
- [Architecture](architecture.md) -- System components, data flow, and design decisions
- [Deployment Guide](deploy.md) -- Kubernetes deployment and troubleshooting
