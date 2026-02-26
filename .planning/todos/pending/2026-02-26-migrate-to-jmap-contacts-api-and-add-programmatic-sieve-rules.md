---
created: 2026-02-26T14:14:04.231Z
title: Migrate to JMAP Contacts API and add programmatic sieve rules
area: api
files:
  - .research/jmap-contacts/research-jmap-contacts-sieve.md
  - .research/jmap-contacts/explore.py
  - src/mailroom/clients/carddav.py
  - src/mailroom/clients/jmap.py
---

## Problem

The current implementation uses CardDAV (XML/vCard) for all contact operations (listing groups, creating contacts, adding members to groups). Fastmail now fully supports RFC 9610 (JMAP for Contacts), which provides JSON-native contact management through the same JMAP session used for email — eliminating the need for a separate CardDAV client, auth flow, and XML parsing.

Additionally, sieve routing rules for contact-group-based email filtering are currently manual (users must create rules via Fastmail UI). Research confirms that Fastmail's `jmapquery` sieve extension supports `fromContactCardUid` with group UIDs, and RFC 9661 (JMAP for Sieve Scripts) may enable programmatic rule management.

## Solution

**Two-phase migration across future milestone(s):**

### Phase A: Replace CardDAV with JMAP Contacts
- New `JMAPContactsClient` using `ContactCard/query`, `ContactCard/get`, `ContactCard/set`
- Groups are `ContactCard` objects with `kind: "group"` and `members` set
- Group UIDs (not JMAP IDs) are stable identifiers used by sieve `fromContactCardUid`
- Remove `CardDAVClient` entirely — single protocol for mail + contacts
- Benefits: JSON instead of XML, batch operations, back-references, incremental sync

### Phase B: Programmatic sieve rule creation
- Check `urn:ietf:params:jmap:sieve` in session capabilities
- If available: push sieve scripts with `jmapquery` blocks via `SieveScript/set`
- If not: explore Fastmail rules import/export as fallback
- Generate rules like: `jmapquery { "fromContactCardUid": "<group-uid>" }` → `fileinto "Triage/Feed"`
- Eliminates the manual sieve step from setup script (Phase 7 current limitation)

### Research completed
Detailed findings in `.research/jmap-contacts/research-jmap-contacts-sieve.md` including:
- Confirmed `urn:ietf:params:jmap:contacts` is live on our Fastmail account
- Documented all current group UIDs and their JMAP IDs
- Mapped every CardDAV operation to its JMAP equivalent
- Stability/risk assessment of Fastmail-proprietary vs RFC-standardized components
- Open item: verify `ContactCard/set` for group membership writes before committing
