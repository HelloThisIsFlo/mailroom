# WIP: Triage Pipeline v2 — How It Works

> **Status:** Work in progress. Will be finalized into proper docs at end of v1.2 milestone.

This document captures the complete triage workflow as designed during v1.2 planning discussions. It serves as the source of truth for how the system is *supposed* to work after all v1.2 phases ship.

---

## Core Concepts

### Categories

A **category** is a bucket for organizing senders. Each category has:

- **name** — e.g., `Imbox`, `Feed`, `Person`, `Billboard`
- **label** — derived as `@To{Name}` (e.g., `@ToPerson`). This is the action label users apply to triage.
- **contact_group** — derived from name. Senders triaged to this category are added to this CardDAV contact group.
- **destination_mailbox** — derived from name. Emails from senders in this category are filed here.
- **contact_type** — `company` (default) or `person`. Determines how the CardDAV contact is created.
- **parent** — optional reference to another category. Establishes a parent-child hierarchy.
- **add_to_inbox** — optional boolean (default: `false`). When `true`, emails filed to this category's destination also appear in Inbox.

### Child Categories Are Independent

A child category (one with `parent` set) is **fully independent**:

- It has its own label, contact group, and destination mailbox — all derived from its own name
- It does **NOT** inherit contact_group, destination_mailbox, or any other field from its parent
- The parent relationship only affects two things:
  1. **Additive contact groups** — sender is added to child's group AND all ancestor groups
  2. **Additive mailbox filing** — emails are filed to child's destination AND all ancestor destinations

### add_to_inbox Flag

The `add_to_inbox` flag controls whether emails also appear in the Inbox:

- **Per-category only** — it is never inherited through the parent chain
- **Screener-only** — only applies to emails that are currently in the Screener mailbox at triage time
- If a parent has `add_to_inbox: true` but its child does not, emails triaged to the child do NOT get Inbox visibility (even though additive filing puts them in the parent's mailbox too)

**Why Screener-only?** Screener is the "sandbox for Inbox" — it holds unsorted incoming mail. When a sender is triaged and their Screener emails are swept, `add_to_inbox` determines if those fresh emails should also appear in Inbox. But when a contact is re-triaged (moved between categories), their existing emails should NOT be re-added to Inbox — they're not new.

### destination_mailbox: Inbox Is Banned

Setting `destination_mailbox: Inbox` is a validation error. Use `add_to_inbox: true` instead. This enforces the separation of concerns: destination is where emails are filed, inbox visibility is a separate flag.

---

## Default Categories

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
|----------|-------|---------------|-------------|--------|-------------|
| Imbox | @ToImbox | Imbox | Imbox | — | true |
| Feed | @ToFeed | Feed | Feed | — | false |
| Paper Trail | @ToPaperTrail | Paper Trail | Paper Trail | — | false |
| Jail | @ToJail | Jail | Jail | — | false |
| Person | @ToPerson | Person | Person | Imbox | false |
| Billboard | @ToBillboard | Billboard | Billboard | Paper Trail | false |
| Truck | @ToTruck | Truck | Truck | Paper Trail | false |

---

## Triage Workflow

### Step-by-step: Triaging a sender to Person (child of Imbox)

1. **User applies action label** — User adds `@ToPerson` to an email from `sender@example.com`
2. **Mailroom detects the label** — The label scanning system finds the labeled email
3. **Contact upserted to additive groups** — Sender is added to:
   - `Person` contact group (the triaged category)
   - `Imbox` contact group (the parent — walking up the full chain)
4. **Emails swept with additive filing** — All emails from this sender currently in Screener are filed to:
   - `Person` mailbox (child's destination)
   - `Imbox` mailbox (parent's destination)
   - Since `Imbox` has `add_to_inbox: true` — **wait, no.** `add_to_inbox` is per-category and Person does NOT have it, so Inbox is NOT added. Only if Person itself had `add_to_inbox: true` would Inbox be added.
   - Since `Person` has `add_to_inbox: false` (default) — no Inbox label added
5. **Action label removed** — `@ToPerson` is removed from the email (last step, for retry safety)

### Step-by-step: Triaging a sender to Imbox (root with add_to_inbox)

1. **User applies** `@ToImbox` to an email
2. **Contact upserted** to `Imbox` contact group
3. **Emails swept** from Screener to:
   - `Imbox` mailbox (destination)
   - `Inbox` (because `add_to_inbox: true` AND emails are from Screener)
4. **Action label removed**

### Step-by-step: Triaging to Billboard (child of Paper Trail)

1. **User applies** `@ToBillboard`
2. **Contact upserted** to:
   - `Billboard` contact group
   - `Paper Trail` contact group (parent)
3. **Emails swept** from Screener to:
   - `Billboard` mailbox
   - `Paper Trail` mailbox
   - No Inbox (neither Billboard nor Paper Trail has `add_to_inbox`)
4. **Action label removed**

### Deep nesting example: Grandparent → Parent → Child

If categories were configured as:
```yaml
- name: Grandparent
  add_to_inbox: true
- name: Parent
  parent: Grandparent
- name: Child
  parent: Parent
```

Triaging to Child:
- **Contact groups:** Child + Parent + Grandparent (full chain)
- **Mailbox labels:** Child + Parent + Grandparent
- **Inbox:** NOT added (Grandparent has `add_to_inbox` but Child does not — it's per-category, never inherited)

Triaging directly to Grandparent:
- **Contact groups:** Grandparent only
- **Mailbox labels:** Grandparent + Inbox (has `add_to_inbox: true`)

---

## Sieve Rules

With additive contact groups, each sieve rule is simple — one contact group maps to one mailbox:

```
Person → sender in "Person" group → file to "Person" mailbox
Imbox → sender in "Imbox" group → file to "Imbox" mailbox
Billboard → sender in "Billboard" group → file to "Billboard" mailbox
Paper Trail → sender in "Paper Trail" group → file to "Paper Trail" mailbox
...
Screener catch-all → all other mail → file to "Screener"
```

The additive filing happens naturally: a Person sender is in both Person and Imbox groups, so both rules fire, and the email gets both mailbox labels. In Fastmail, mailboxes are labels — the email appears in both folders.

**add_to_inbox and sieve:** Sieve rules DO handle `add_to_inbox`. Categories without the flag get an "archive" action (removes Inbox label). Categories with the flag skip archive (email stays in Inbox). See rule setup below.

**Rule setup in Fastmail UI:**

Standard category (no `add_to_inbox`) — 3 actions:
1. Add label: `{destination_mailbox}`
2. Archive (remove Inbox label)
3. Continue to apply other rules

Category with `add_to_inbox: true` — 2 actions:
1. Add label: `{destination_mailbox}`
2. Continue to apply other rules (NO archive — stays in Inbox)

**Critical: "Continue to apply other rules"** must be enabled on ALL category rules. Without it, additive labels from parent/child rules won't fire. This is the most common setup mistake.

---

## Re-triage (Group Change)

> Phase 13 scope — captured here for completeness.

When a sender is re-triaged (moved from one category to another):

1. **Contact moved to new additive groups** — Added to new child + parent groups, removed from old groups
2. **All emails from contact re-filed** — Fetch all emails from this sender (not just Screener), apply the new additive mailbox labels
3. **add_to_inbox NOT applied on re-triage** — Only Screener emails get Inbox. Re-triage doesn't add Inbox because these emails aren't new
4. **Triage history captured** — Contact note records the move

### Sweep logic on re-triage

The sweep on re-triage is broader than initial triage:
- **Initial triage:** sweep Screener emails only → apply additive labels + optional Inbox
- **Re-triage:** fetch ALL emails from contact (any mailbox) → apply new additive labels, do NOT add Inbox

This means `_get_destination_mailbox_ids` (or its replacement) needs to:
1. Walk the parent chain to collect all ancestor destinations
2. Check `add_to_inbox` on the triaged category (not parents) — add Inbox only if true AND email is from Screener
3. Return the full list of mailbox IDs to apply

---

## Validation Rules

At startup, the config validator checks:

1. At least one category required
2. No duplicate names
3. All parent references point to existing categories
4. No circular parent chains
5. No duplicate labels after derivation
6. `destination_mailbox: Inbox` is rejected (use `add_to_inbox` instead)
7. No shared contact groups unless related via parent chain

---

*WIP document — will be finalized at end of v1.2 milestone.*
