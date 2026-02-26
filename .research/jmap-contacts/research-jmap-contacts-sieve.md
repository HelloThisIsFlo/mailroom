# Research: Fastmail JMAP Contacts API & Sieve Contact Group Filtering

**Date:** 2026-02-26
**Context:** Investigating how to programmatically filter incoming emails by contact group membership in Fastmail, for the HEY-style screener/routing system (mailroom project).

---

## Goal

Determine whether we can:
1. Get contact group IDs programmatically (without manual UI interaction)
2. Use those IDs in Sieve rules to route emails based on contact group membership
3. Replace CardDAV with JMAP for all contact operations
4. Create/manage rules programmatically

---

## Key Discovery: `fromContactCardUid`

The Sieve `jmapquery` extension uses the property **`fromContactCardUid`** with the **UID** (not the JMAP ID) of a contact group to match incoming emails from senders who are members of that group.

Example from Fastmail's auto-generated Sieve:

```sieve
# Rule Feed
# Search: "fromin:Feed"
if allof(
  not string :is "${stop}" "Y",
  jmapquery text:
  {
     "fromContactCardUid" : "a1ecd105-2e22-4bb8-8ea9-1aa6538d292e"
  }
.
) {
  if mailboxidexists "P0Sw" {
    set "L2_Feed" "Y";
    set "skipinbox" "Y";
  }
}
```

---

## RFC 9610 (JMAP for Contacts) — Fully Live on Fastmail

### Status

- **Published:** December 2024
- **Status:** Proposed Standard (same maturity as JMAP Core and JMAP Mail)
- **Author:** Neil Jenkins (Fastmail)
- **Capability URI:** `urn:ietf:params:jmap:contacts`

### Confirmed on Our Account

The JMAP session at `https://api.fastmail.com/jmap/session` confirms:
- `urn:ietf:params:jmap:contacts` is present in both `capabilities` and `accountCapabilities`
- Account `u5bde4052` (flo@kempenich.ai) has `isReadOnly: false`
- `mayCreateAddressBook: false` (but we don't need that — we just need to read/write ContactCards)
- The legacy proprietary `ContactGroup/get` method is **gone** (returns `unknownMethod`)

### Data Model

In RFC 9610, contact groups are represented as `ContactCard` objects with:
- `kind: "group"` — distinguishes groups from individual contacts
- `members` — a set of UIDs referencing other ContactCards that are members
- `uid` — a stable identifier (this is what Sieve's `fromContactCardUid` uses)
- `id` — the JMAP object ID (different from `uid`)
- `name` — the display name (e.g., `{ "full": "Feed" }`)

### API Methods Available

| Method | Purpose | Read/Write |
|--------|---------|------------|
| `ContactCard/query` | Search/filter contacts | Read |
| `ContactCard/get` | Fetch contact details by ID | Read |
| `ContactCard/set` | Create, update, delete contacts | Write |
| `ContactCard/changes` | Incremental sync | Read |
| `AddressBook/get` | List address books | Read |

### Querying Groups Programmatically

```json
{
  "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:contacts"],
  "methodCalls": [
    ["ContactCard/query", {
      "accountId": "u5bde4052",
      "filter": { "kind": "group" }
    }, "0"],
    ["ContactCard/get", {
      "accountId": "u5bde4052",
      "#ids": { "resultOf": "0", "name": "ContactCard/query", "path": "/ids" }
    }, "1"]
  ]
}
```

---

## Current Contact Groups (as of 2026-02-26)

| Group | UID (for Sieve `fromContactCardUid`) | JMAP ID | Members |
|-------|--------------------------------------|---------|---------|
| Imbox | `7a27eebf-e448-47ed-81d1-4be6243c4ad2` | `D-JQn` | 10 |
| Feed | `a1ecd105-2e22-4bb8-8ea9-1aa6538d292e` | `D0ms` | 3 |
| Paper Trail | `2d7fde48-c549-43cd-a0ac-7f93984a1ddd` | `D0mg` | 13 |
| Jail | `6cbd2e84-16de-4ed2-9df7-d41c6a7e4ad9` | `D-Ia5` | 1 |
| VIPs | `vips` | `D09-` | 3 |
| Autosaved | `fcdcc9b2-88e1-404c-b8b7-d177a35a54fd` | `D0m-` | 2 |
| z iCloud Imported 20260219 | `5C3D19B0-0DD3-11F1-99D5-A3AA52036B07` | `D05g` | 328 |

---

## Sieve Architecture on Fastmail

### How It Works

- Fastmail auto-generates Sieve code from rules created in the UI
- Custom Sieve can be added in 4 editable sections between auto-generated blocks
- Code runs top-to-bottom; order matters
- Edit at: Settings → Filters & Rules → "Edit custom Sieve code"
- Test at: `https://app.fastmail.com/sievetester/`
- Rules can be exported/imported as JSON at Settings → Filters & Rules

### `vnd.cyrus.jmapquery` Extension

This is a Fastmail/Cyrus-specific Sieve extension that accepts a JMAP `Email/query` filter as a JSON blob inside a Sieve multi-line string literal.

Syntax:
```sieve
if jmapquery text:
{
   "property" : "value"
}
.
{
  # actions
}
```

The JSON supports standard JMAP Email/query FilterCondition properties plus Fastmail-specific ones:
- `from` — match sender
- `header` — match headers as `["Header-Name", "value"]`
- `conditions` / `operator` — AND/OR combinators
- `fromContactCardUid` — match sender against members of a contact group (Fastmail-specific)

### Supported Sieve Extensions

```
require ["fileinto", "reject", "vacation", "envelope", "body", "relational",
  "regex", "subaddress", "copy", "mailbox", "mboxmetadata", "servermetadata",
  "date", "index", "comparator-i;ascii-numeric", "variables", "imap4flags",
  "editheader", "duplicate", "vacation-seconds", "fcc", "vnd.cyrus.jmapquery",
  "vnd.cyrus.log", "mailboxid", "special-use", "vnd.cyrus.snooze",
  "vnd.cyrus.imip", "vnd.cyrus.implicit_keep_target"];
```

### How Fastmail's Generated Rules Work (Internal Variables)

When the UI creates a rule, the generated Sieve uses a two-phase approach:
1. **Matching phase:** Tests conditions, sets a variable like `L2_Feed` to `"Y"`
2. **Action phase:** Checks variables, performs `fileinto`, sets `hasmailbox`, `skipinbox`, etc.

Key internal variables:
- `${stop}` — if "Y", skip all remaining rules
- `${hasmailbox}` — email was given a label/folder
- `${skipinbox}` — email should be archived (removed from inbox)
- `${deletetotrash}` — email should go to trash
- `${spam}` — email should go to spam
- `${read}` — mark as read
- `${flagged}` — mark as flagged

Custom Sieve placed at the end of the script can check these variables to implement catch-all logic (e.g., the mailing list catch-all pattern from the Charles Strahan blog post).

### Existing Rules (from export)

| Rule | Search | Action |
|------|--------|--------|
| Jail | `fromin:Jail` | File to Jail, skip inbox |
| Paper Trail | `fromin:"Paper Trail"` | File to Paper Trail, skip inbox |
| Feed | `fromin:Feed` | File to Feed, skip inbox |
| Feed - Seth Godin | `from:notify@sethgodin.com` | File to Feed/Seth Godin |
| Paper Trail - Invoice - Apple | `from:no_reply@email.apple.com subject:Invoice` | File to Paper Trail/Invoices, mark read, stop |
| _Screener | `NOT fromin:contacts` | File to Inbox/Screener, stop |

---

## Can CardDAV Be Replaced?

**Yes.** RFC 9610 via JMAP covers everything CardDAV was used for:

| Operation | CardDAV | JMAP (RFC 9610) |
|-----------|---------|-----------------|
| List contacts | GET collection | `ContactCard/query` + `ContactCard/get` |
| Create contact | PUT vCard | `ContactCard/set` (create) |
| Update contact | PUT vCard | `ContactCard/set` (update) |
| Delete contact | DELETE | `ContactCard/set` (destroy) |
| List groups | GET + filter KIND:group | `ContactCard/query` with `filter: { kind: "group" }` |
| Add member to group | PUT vCard with updated MEMBER | `ContactCard/set` (update `members` property) |

**Advantages of JMAP over CardDAV:**
- Same protocol as email operations (single auth token, single HTTP client)
- JSON instead of XML/vCard
- Batch operations in a single request
- Back-references between method calls
- Incremental sync via `ContactCard/changes`

**Action needed:** Verify that `ContactCard/set` works for modifying the `members` property on group cards before fully committing. A quick test with a throwaway contact would confirm.

---

## Can Rules Be Created Programmatically?

### Option 1: JMAP for Sieve Scripts (RFC 9661)

Published 2024, same vintage as contacts. Check if `urn:ietf:params:jmap:sieve` appears in the session capabilities. If so, you can push raw Sieve scripts containing `jmapquery` blocks directly via the API.

**Not yet confirmed** — needs a session capability check.

### Option 2: Fastmail Proprietary Rules API

Fastmail's UI creates rules via internal JMAP method calls. Whether these are exposed to third-party API tokens is unknown. Could probe for methods like `MailRule/get` or check session for Fastmail-specific capabilities.

### Option 3: Direct Sieve Editing

Even without a rules API, you can manage the Sieve script itself — either via the Sieve API (if available) or by exporting, modifying, and re-importing the rules JSON. The import/export is available at Settings → Filters & Rules.

---

## Stability & Risk Assessment

### Fully Standardised (safe to build on permanently)

| Component | Standard | Published |
|-----------|----------|-----------|
| JMAP Core | RFC 8620 | July 2019 |
| JMAP Mail | RFC 8621 | August 2019 |
| JMAP Contacts | RFC 9610 | December 2024 |
| JSContact (card format) | RFC 9553 | 2024 |
| ContactCard `uid` field | RFC 9553 §2.1.9 | 2024 |
| CardDAV (fallback) | RFC 6352 | 2011 |

### Practically Stable (Fastmail-proprietary but locked in)

| Component | Reasoning |
|-----------|-----------|
| `fromContactCardUid` in `jmapquery` | Fastmail's own rules UI generates it; `fromin:` search depends on it; thousands of user rules use it. Changing it would break Fastmail's own product. |
| `vnd.cyrus.jmapquery` Sieve extension | Baked into Cyrus IMAP (which Fastmail maintains). Listed in Fastmail's require block. |
| Fastmail's internal Sieve variable system (`${stop}`, `${hasmailbox}`, etc.) | Used by all auto-generated rules. |

### Unknown / Higher Risk

| Component | Risk |
|-----------|------|
| Any proprietary rules management API | Internal, undocumented, could change |
| Specific mailbox IDs in Sieve (e.g., `P0Sw`) | Change if mailboxes are recreated |

**Worst-case scenario:** A future Cyrus upgrade renames `fromContactCardUid`. You'd update a single string in your code. You'd know immediately because rules would stop matching.

---

## Programmatic Flow for the Screener

The complete chain, no manual steps:

```
1. ContactCard/query (filter: kind=group)
   → Get all groups with UIDs

2. ContactCard/get (fetch individual contact by UID)
   → Read member lists, email addresses

3. ContactCard/set (update members on group card)
   → Add sender to Feed/Paper Trail/Imbox group

4. Sieve rules with jmapquery
   → { "fromContactCardUid": "<group-uid>" }
   → Routes future emails from group members automatically

5. Email/query + Email/set (JMAP Mail)
   → Poll for triage labels, extract sender, remove label
```

---

## Key URLs & References

| Resource | URL |
|----------|-----|
| Fastmail JMAP Session | `https://api.fastmail.com/jmap/session` |
| Fastmail JMAP API | `https://api.fastmail.com/jmap/api/` |
| Fastmail Sieve Editor | Settings → Filters & Rules → "Edit custom Sieve code" |
| Fastmail Sieve Tester | `https://app.fastmail.com/sievetester/` |
| RFC 9610 (JMAP Contacts) | https://www.rfc-editor.org/rfc/rfc9610.html |
| RFC 8621 (JMAP Mail) | https://www.rfc-editor.org/rfc/rfc8621.html |
| RFC 8620 (JMAP Core) | https://www.rfc-editor.org/rfc/rfc8620.html |
| JMAP Contacts Spec (jmap.io) | https://jmap.io/spec-contacts.html |
| Fastmail Sieve Docs | https://www.fastmail.help/hc/en-us/articles/1500000280481 |
| Fastmail Sieve Examples | https://www.fastmail.help/hc/en-us/articles/360058753794 |
| Fastmail Sieve How-To | https://www.fastmail.help/hc/en-us/articles/360060591373 |
| Fastmail Sieve FAQ | https://www.fastmail.help/hc/en-us/articles/360058753814 |
| Charles Strahan Blog (jmapquery examples) | https://www.cstrahan.com/blog/taming-email-with-fastmail-rules/ |
| Julia Evans JMAP Quickstart | https://jvns.ca/blog/2020/08/18/implementing--focus-and-reply--for-fastmail/ |
| Fastmail JMAP Samples (GitHub) | https://github.com/fastmail/JMAP-Samples |

---

## Open Action Items

1. **Verify `ContactCard/set` for group membership** — Test adding a UID to a group's `members` via JMAP to confirm write access works as expected
2. **Check for `urn:ietf:params:jmap:sieve` in session** — Would enable programmatic Sieve script management
3. **Decide: CardDAV removal** — If `ContactCard/set` works for groups, remove CardDAV dependency from the screener
4. **Consider: Programmatic rule creation** — Either via Sieve API or rule import/export
