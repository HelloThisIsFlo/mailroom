# Pitfalls Research

**Domain:** Fastmail email triage automation (JMAP + CardDAV)
**Researched:** 2026-02-23
**Confidence:** MEDIUM (based on training data for JMAP/CardDAV protocols and Fastmail implementation; web verification tools unavailable during research)

## Critical Pitfalls

### Pitfall 1: JMAP Session URL Hardcoding

**What goes wrong:**
Developers hardcode the JMAP API URL (e.g., `https://api.fastmail.com/jmap/api/`) instead of discovering it from the session resource. The JMAP spec requires clients to first GET the session resource (`https://api.fastmail.com/jmap/session`), which returns the actual API URL, upload URL, download URL, and account IDs. Fastmail can change these URLs at any time. Hardcoding means the service silently breaks when Fastmail updates their infrastructure.

**Why it happens:**
The session resource seems like an unnecessary extra step -- the API URL has been stable for years. Developers skip it to simplify code and because it "works." The session resource also contains account capabilities, account IDs, and state information that are easy to ignore when you only care about sending requests.

**How to avoid:**
Always fetch the session resource on startup and cache it. Re-fetch on any `urn:ietf:params:jmap:error:unknownMethod` or HTTP 404 responses. The session response includes `apiUrl`, `downloadUrl`, `uploadUrl`, and `eventSourceUrl` -- use all of them from the session, never hardcode. Also extract the primary account ID from the session's `primaryAccounts` object rather than hardcoding it.

**Warning signs:**
- Any hardcoded URL containing `/jmap/api/` in source code
- Account ID stored in config rather than extracted from session
- No session fetch in the startup sequence

**Phase to address:** Phase 1 (JMAP foundation). Get session management right from the first line of code.

---

### Pitfall 2: CardDAV ETag / If-Match Concurrency Violations

**What goes wrong:**
When updating a contact (e.g., adding it to a contact group), the code fetches the vCard, modifies it, and PUTs it back -- but without sending the `If-Match` header with the ETag from the GET response. If the contact was modified between the GET and PUT (by another client, by Fastmail's own sync, or by the user editing the contact on their phone), the update silently overwrites those changes. Alternatively, the server may reject the PUT with a 412 Precondition Failed and the code does not handle this.

**Why it happens:**
CardDAV's optimistic concurrency model is easy to ignore in a single-writer scenario. Developers think "I'm the only one modifying contacts programmatically, so there is no conflict." But the user edits contacts on their phone, Fastmail web, and other devices. The contact the service just fetched may have been updated by the user adding a phone number or note.

**How to avoid:**
Always store the ETag from the GET response. Always send `If-Match: "<etag>"` on PUT. Handle 412 responses by re-fetching the contact, re-applying the group change, and re-PUTting. This retry loop should be bounded (3 attempts max) to prevent infinite loops during rapid user editing.

**Warning signs:**
- PUT requests to CardDAV without `If-Match` header
- No 412 error handling in CardDAV client code
- User reports that contact edits (phone numbers, notes) are disappearing

**Phase to address:** Phase 2 (CardDAV integration). Must be in the initial CardDAV implementation, not retrofitted.

---

### Pitfall 3: Contact Group Membership Model Confusion (KIND:group vCard vs. CATEGORIES)

**What goes wrong:**
Fastmail implements contact groups as separate vCards with `KIND:group` property and `MEMBER:` entries (RFC 6350 group vCard model), NOT as `CATEGORIES` properties on individual contact vCards. Developers who assume groups are stored as categories on each contact will write code that either (a) creates CATEGORIES properties that Fastmail ignores for rule matching, or (b) fails to find existing group memberships. The Fastmail rules engine matches on contact group membership, not CATEGORIES -- so using the wrong model means senders are never routed correctly.

**Why it happens:**
Both models exist in the vCard/CardDAV ecosystem. Apple Contacts uses the `KIND:group` + `MEMBER:` model. Google Contacts uses a proprietary model. Some servers use CATEGORIES. Without reading Fastmail's specific implementation docs, developers guess wrong. The CATEGORIES approach is simpler (modify the contact, done), so it is the first thing developers try.

**How to avoid:**
Use the `KIND:group` vCard model:
1. Fetch the contact group vCard (it has `KIND:group` property)
2. Add a `MEMBER:urn:uuid:<contact-uuid>` line pointing to the contact's UID
3. PUT the group vCard back (with ETag handling)

To add a sender to a group:
- First, create or find the contact vCard for the sender (GET + search by email, or create new)
- Note the contact's UID
- Fetch the group vCard
- Add `MEMBER:urn:uuid:<contact-uid>` to the group vCard
- PUT the group vCard back

The group vCards can be found by fetching the entire address book and filtering for vCards where `KIND` equals `group` and `FN` (display name) matches the target group name.

**Warning signs:**
- Code that modifies CATEGORIES on individual contacts
- Contact added but Fastmail rules do not route email correctly
- Groups appear empty in Fastmail web UI despite code claiming success

**Phase to address:** Phase 2 (CardDAV integration). This is THE critical correctness requirement. Prototype and verify against Fastmail before building the full pipeline.

---

### Pitfall 4: Polling Loop Drift and Missed Emails

**What goes wrong:**
The polling implementation uses `time.sleep(300)` in a loop, but does not track state between polls. Each poll queries "emails with triage labels" -- but if the JMAP query has pagination and the code does not paginate, it only processes the first page. More subtly, if the code does not track which emails it has already processed (by message ID or UID), a failure during processing (e.g., CardDAV is down) leaves the triage label in place, which is correct for retry -- but the code may also re-process emails that were already successfully handled if it crashed mid-batch.

**Why it happens:**
Simple polling loops are deceptively easy to write and hard to make correct. The happy path works, but edge cases around partial failures, restarts, and duplicate processing are missed.

**How to avoid:**
- Always paginate JMAP queries (use `position` and `limit` parameters, follow `hasMoreResults`)
- Use the triage label itself as the work queue -- only emails with the triage label need processing, and removing the label after success is the "ack." This is already in the design, which is good.
- Process one sender at a time, not one email at a time. Fetch all triage-labeled emails, group by sender, process each sender atomically (add to group, sweep all emails, remove triage labels). If any step fails for a sender, leave all their triage labels intact.
- Log which sender/email is being processed before and after each step, so crash recovery is diagnosable from logs.

**Warning signs:**
- `time.sleep()` at the end of the loop body (use sleep at the start, or between iterations -- though this is minor)
- No pagination in JMAP Email/query calls
- Processing emails individually rather than grouped by sender
- No structured logging of processing steps

**Phase to address:** Phase 1 (JMAP foundation) for query pagination. Phase 3 (triage pipeline) for sender-grouped processing.

---

### Pitfall 5: vCard 3.0 vs 4.0 Format Mismatch

**What goes wrong:**
Fastmail stores contacts in vCard 3.0 format. Python vCard libraries (like `vobject`) can parse both 3.0 and 4.0, but generating output defaults may vary. If the code creates new contacts in vCard 4.0 format, or if edits to existing contacts accidentally change the VERSION property or introduce 4.0-only properties, Fastmail may reject the PUT or -- worse -- silently accept it but lose data or break the contact in the Fastmail UI.

**Why it happens:**
Developers often do not pay attention to vCard version when constructing contacts programmatically. The RFC 6350 (vCard 4.0) `KIND:group` property is actually a 4.0 feature, yet Fastmail uses it in what they advertise as 3.0 contacts. This hybrid situation is confusing. Libraries may "upgrade" the format during serialization.

**How to avoid:**
- When creating new contacts, explicitly set `VERSION:3.0`
- When modifying existing contacts, preserve the original vCard format as much as possible -- parse, modify only the fields you need, re-serialize
- Test with Fastmail specifically: create a contact via CardDAV, verify it appears correctly in Fastmail web UI and iOS app
- Use `vobject` library and be explicit about serialization format
- For group vCards, test that Fastmail accepts the `KIND:group` + `MEMBER:` format over CardDAV specifically (not just in theory)

**Warning signs:**
- New contacts appear in Fastmail but display incorrectly (missing fields, garbled text)
- CardDAV PUT returns 200 but contact does not appear in UI
- vCard library emitting `VERSION:4.0` in output

**Phase to address:** Phase 2 (CardDAV integration). Needs manual verification against live Fastmail during development.

---

### Pitfall 6: Duplicate Contact Creation

**What goes wrong:**
When a triage label is applied, the service needs to find or create a contact for the sender. If the "find" step is incorrect -- searching by email address but not finding an existing contact because the search query format is wrong, or because the sender already exists with a different email capitalization -- the service creates a duplicate contact. Over time, the address book fills with duplicates, and the user has two contacts for the same person (one in a group, one not).

**Why it happens:**
CardDAV does not have a native "find contact by email" query. You must either: (a) fetch the entire address book and search locally, (b) use a REPORT query with a text-match filter, or (c) use Fastmail's proprietary search if available. Option (a) is expensive but reliable. Option (b) depends on server support for the filter. Email addresses are also case-insensitive per RFC, but string matching is case-sensitive by default.

**How to avoid:**
- On startup, fetch the full address book and build an in-memory index of email-to-contact-UID mappings
- Normalize all email addresses to lowercase before comparison
- Refresh the index periodically (every poll cycle is overkill; every 10 cycles or on contact creation is sufficient)
- When creating a new contact, immediately add it to the local index
- Use CardDAV `addressbook-query` REPORT with `text-match` filter as a secondary check if available, but do not rely on it exclusively

**Warning signs:**
- User sees duplicate contacts in Fastmail contacts
- Same sender triaged twice creates two contacts
- Contact search returns empty for a sender who was already triaged

**Phase to address:** Phase 2 (CardDAV integration). The contact lookup strategy must be designed before any contact creation code is written.

---

### Pitfall 7: JMAP Mailbox ID vs. Label Name Confusion

**What goes wrong:**
JMAP does not use label names (like "Screener" or "@ToImbox") directly. Emails are associated with Mailboxes, which have internal IDs. The code must first query `Mailbox/get` to find the mailbox ID for each label name, then use those IDs in `Email/query` filters and `Email/set` updates. Developers who hardcode mailbox IDs (copied from one API response during development) will break when the user recreates a label, or across different accounts.

**Why it happens:**
Fastmail labels are Mailboxes in JMAP. The API documentation says Mailbox, not label. The mismatch between Fastmail's UI terminology ("labels") and JMAP's terminology ("mailboxes") confuses developers. Also, mailbox IDs look like random strings, so developers hardcode them thinking they are stable.

**How to avoid:**
- On startup, call `Mailbox/get` to fetch all mailboxes
- Build a name-to-ID mapping (use the `name` property)
- Refresh this mapping if a `Mailbox/get` call returns unexpected results
- Store mailbox names in config (ConfigMap), never IDs
- Handle the case where a label does not exist (log error, skip, do not crash)

**Warning signs:**
- Mailbox IDs in configuration files or environment variables
- `Email/query` calls with hardcoded mailbox IDs
- "mailbox not found" errors after label recreation

**Phase to address:** Phase 1 (JMAP foundation). Mailbox resolution is the first thing the JMAP client needs to do.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Fetch full address book every poll cycle | Simpler code, no local state | Wastes bandwidth, slow for large address books, may hit rate limits | Only during early prototyping; replace with cached index before production |
| Single-file `main.py` | Fast to write, easy to understand | Hard to test, hard to extend for future workflows, mixing concerns | MVP only; refactor into modules before adding second workflow |
| No retry backoff on API failures | Simpler error handling | Hammers Fastmail API during outages, may get rate-limited or blocked | Never -- always use exponential backoff |
| Storing JMAP session in memory only | No persistence needed | Session re-fetch on every restart (minor, acceptable) | Always acceptable for a polling service |
| Not validating vCard after creation | Faster development | Silent data corruption in contacts | Only during initial development; add validation before production |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| JMAP Authentication | Using the user's main password instead of an API token (app-specific password) | Generate a dedicated API token at Fastmail Settings > Privacy & Security > Manage API tokens. Use `Authorization: Bearer <token>` header. |
| CardDAV Authentication | Using the same JMAP API token for CardDAV | CardDAV requires a separate app password (HTTP Basic auth), not the JMAP bearer token. Generate at Settings > Privacy & Security > Third-party apps. Use HTTP Basic Auth with username + app password. |
| JMAP Email/set for label changes | Using `Email/set` with `update` to set `mailboxIds` as a complete replacement object, accidentally removing the email from all other mailboxes | Use the patch syntax: `"mailboxIds/<newId>": true` to add a mailbox, `"mailboxIds/<oldId>": null` to remove. Never send the full `mailboxIds` object unless you intend to replace all associations. |
| CardDAV URL path | Using the wrong CardDAV path format | Fastmail CardDAV base URL is `https://carddav.fastmail.com/dav/addressbooks/user/<email>/Default/`. The trailing slash matters. The address book name is typically `Default`. |
| JMAP method call ordering | Sending independent method calls as separate HTTP requests | JMAP supports batching multiple method calls in a single request. Use this for efficiency (e.g., `Mailbox/get` + `Email/query` in one round-trip). Method calls within a request are processed in order and can reference results from earlier calls using `#` back-references. |
| CardDAV contact UID | Generating a UID that collides with existing contacts, or not setting a UID at all | Always generate a UUID v4 for new contacts. Set it as both the `UID` property in the vCard and the filename in the PUT URL (e.g., `PUT .../Default/<uuid>.vcf`). |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Fetching full address book every poll cycle | Slow polls, high memory usage, timeouts for accounts with thousands of contacts | Cache the address book in memory, use CardDAV sync (ctag/sync-token) to detect changes and only re-fetch when changed | Over 500 contacts (noticeable slowdown), over 2000 contacts (may timeout) |
| Not using JMAP request batching | Multiple round-trips per poll cycle, slow processing, higher latency | Batch related JMAP calls into single requests using back-references | Always slower than necessary; becomes noticeable at >5s poll processing time |
| Fetching full email bodies when only headers needed | Excessive bandwidth, slow queries, wasted memory | Use JMAP `Email/get` with `properties` parameter to request only `from`, `mailboxIds`, `keywords` -- never fetch `bodyValues` or `htmlBody` unless needed | Noticeable immediately with emails containing large attachments |
| Processing all triage labels in sequence without batching | Each sender requires separate CardDAV round-trips; 10 triaged senders = 10+ seconds of sequential processing | Group all operations, batch JMAP calls, but CardDAV operations must be sequential per-contact (due to ETag concurrency) | Over 5 triaged senders in one poll cycle |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Committing the Kubernetes Secret YAML with actual credentials | API token and app password exposed in git history | Use a `secret.yaml.template` with placeholder values. Document that real values must be applied via `kubectl create secret` command. Add `k8s/secret.yaml` to `.gitignore`. |
| Logging email content or full headers | Email content in logs is a privacy risk, especially on shared infrastructure | Only log: sender address, mailbox/label names, action taken, timestamps. Never log subject lines, body content, or full headers. |
| Using the main Fastmail account password | If compromised, attacker has full account access; cannot be scoped or revoked independently | Always use app-specific passwords/API tokens. These can be revoked without affecting the main password and can be scoped to specific services. |
| Running the container as root | Privilege escalation risk in Kubernetes | Set `runAsNonRoot: true` and `runAsUser: 1000` in the pod security context. Use a non-root user in the Dockerfile. |
| No network policy in Kubernetes | Pod can communicate with any other pod or external service | Apply a NetworkPolicy that limits egress to Fastmail API endpoints only (api.fastmail.com, carddav.fastmail.com). Not critical for a home cluster but good practice. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent failures -- service fails but no indication to user | User applies triage label, nothing happens, emails stay in Screener indefinitely, user loses trust | Keep the triage label in place on failure (already planned). Additionally, consider a simple health check endpoint or at minimum clear structured logs the user can query. |
| Processing delay feels broken | User applies label, expects immediate action, checks 30 seconds later and nothing happened (next poll is 4.5 minutes away) | Document expected delay (up to 5 minutes). Consider a shorter initial poll interval (1 minute) that backs off when idle. |
| Triage label on wrong email from sender | User applies @ToFeed to one email but has multiple emails from that sender; ALL are swept | This is the intended behavior (documented in PROJECT_BRIEF). Make it very clear in README that triage is per-sender, not per-email. |
| Contacts created with email address as display name | Address book fills with entries like "noreply@company.com" instead of "Company Name" | Extract the sender display name from the `From` header (`"Company Name" <email@company.com>`) and use it as the `FN` (Full Name) property in the vCard. Fall back to email address only when no display name is provided. |

## "Looks Done But Isn't" Checklist

- [ ] **JMAP Email/query pagination:** Often missing full pagination -- verify that `hasMoreResults` is checked and subsequent pages are fetched. A test with >50 triage-labeled emails should pass.
- [ ] **CardDAV group membership removal:** Adding to a group works, but removing from a previous group is missed. If a sender was in Jail and gets re-triaged to Imbox, the old Jail membership must be removed. Verify that re-triage works correctly.
- [ ] **Email sweep completeness:** The sweep of Screener emails for a sender should match on the actual email address, not just a substring. `from:alice@example.com` should not match `alice@example.company.com`. Verify the JMAP filter uses exact `from` matching.
- [ ] **Triage label removal atomicity:** The triage label should only be removed AFTER the contact group update AND the email sweep succeed. If label removal happens first but subsequent steps fail, the email is lost from the retry queue. Verify ordering.
- [ ] **Multiple triage labels on same email:** What happens if a user applies both `@ToFeed` and `@ToImbox` to the same email? The code must handle this gracefully (pick one, log a warning, not crash).
- [ ] **Empty From header:** Some emails have malformed or missing From headers. The code must handle this without crashing (log and skip the email).
- [ ] **Contact already in a different group:** If a contact is already in "Feed" and gets triaged to "Imbox," the code must remove from Feed group AND add to Imbox group. Verify this is not just "add to new group."

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Duplicate contacts created | LOW | Write a one-time script to find contacts with duplicate emails, merge group memberships to one, delete the other. Fastmail web UI also has a "merge duplicates" feature. |
| Wrong group membership model (CATEGORIES instead of KIND:group) | HIGH | Must rewrite the entire CardDAV integration. All "group assignments" done via CATEGORIES are ineffective. Need to redo all triage operations. Keep a log of all triage actions so they can be replayed. |
| Hardcoded mailbox IDs break after label recreation | LOW | Update the code to resolve by name. Re-run the service. No data loss -- emails still have labels, just the service could not find them temporarily. |
| ETag conflicts causing lost contact edits | MEDIUM | Audit contacts for missing phone numbers, notes, etc. that were overwritten. No automated recovery -- user must manually re-add lost data. Prevention is far cheaper than recovery. |
| vCard format issues corrupting contacts | MEDIUM | Export affected contacts, fix vCard format, re-import. Fastmail's import/export in Contacts settings can help. |
| Polling loop crashes and does not restart | LOW | Kubernetes restarts the pod automatically (restartPolicy: Always). Ensure the Deployment has liveness/readiness probes or at minimum relies on process exit code for restart. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| JMAP session URL hardcoding | Phase 1: JMAP Foundation | Code review: no hardcoded URLs; session fetch on startup; account ID from session |
| CardDAV ETag concurrency | Phase 2: CardDAV Integration | Test: modify contact in Fastmail UI between GET and PUT; verify no data loss |
| Contact group model confusion (KIND:group) | Phase 2: CardDAV Integration | Test: add contact to group via code, verify it appears in group in Fastmail web UI AND triggers rule routing |
| Polling loop drift / missed emails | Phase 3: Triage Pipeline | Test: triage 100+ emails across 20 senders in one cycle; verify all processed |
| vCard 3.0/4.0 format mismatch | Phase 2: CardDAV Integration | Test: create contact via CardDAV, view in Fastmail iOS app, verify all fields display correctly |
| Duplicate contact creation | Phase 2: CardDAV Integration | Test: triage same sender twice; verify only one contact exists |
| Mailbox ID vs name confusion | Phase 1: JMAP Foundation | Code review: all mailbox references use name-based lookup; no IDs in config |
| JMAP Email/set patch syntax | Phase 1: JMAP Foundation | Test: add label to email, verify other labels preserved; remove label, verify email not removed from other mailboxes |
| CardDAV auth vs JMAP auth | Phase 2: CardDAV Integration | Separate credentials in config; test each independently |
| Silent failures | Phase 4: Observability & Hardening | Structured log output verified; health check or error logging in place |
| Multiple triage labels on same email | Phase 3: Triage Pipeline | Test: apply two triage labels to one email; verify graceful handling |
| Contact re-triage (group transfer) | Phase 3: Triage Pipeline | Test: triage sender to Feed, then re-triage to Imbox; verify removed from Feed group, added to Imbox group |

## Sources

- JMAP Core Specification (RFC 8620) -- session resource, method calls, error handling [MEDIUM confidence: from training data, not verified against current spec]
- JMAP Mail Specification (RFC 8621) -- Email/query, Email/set, Mailbox operations [MEDIUM confidence: from training data]
- vCard 4.0 Specification (RFC 6350) -- KIND:group, MEMBER property [MEDIUM confidence: from training data]
- CardDAV Specification (RFC 6352) -- ETag handling, address book queries [MEDIUM confidence: from training data]
- Fastmail developer documentation (https://www.fastmail.com/dev/) -- JMAP endpoint, auth methods [MEDIUM confidence: from training data, URL not verified as current]
- Fastmail JMAP Samples (https://github.com/fastmail/JMAP-Samples) -- reference implementation patterns [MEDIUM confidence: known repository from training data]
- Julia Evans blog post on Fastmail JMAP (https://jvns.ca/blog/2020/08/18/implementing--focus-and-reply--for-fastmail/) -- practical JMAP usage patterns [MEDIUM confidence: referenced in PROJECT_BRIEF]
- General CardDAV/vCard interoperability experience across providers [LOW confidence: synthesized from training data patterns]

**Note:** Web search and web fetch tools were unavailable during this research. All findings are based on training data knowledge of JMAP/CardDAV protocols and Fastmail's implementation. Critical pitfalls (especially #3: contact group model, and #5: vCard format) should be validated against live Fastmail during Phase 2 development before building the full pipeline.

---
*Pitfalls research for: Fastmail email triage automation (JMAP + CardDAV)*
*Researched: 2026-02-23*
