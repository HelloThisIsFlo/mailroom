# Phase 3: Triage Pipeline - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

The complete screener workflow runs end-to-end: poll for triaged emails, process each sender (upsert contact into group, sweep Screener emails, relabel for destination, remove triage label), with retry safety on failure. Covers TRIAGE-01 through TRIAGE-06.

</domain>

<decisions>
## Implementation Decisions

### Sweep destination behavior
- Every swept email gets: Screener label removed + destination label added
- The triggering email (has both Screener + action label) gets both labels removed, destination label added
- Other emails from same sender in Screener (Screener label only) get Screener removed, destination label added
- Destination label mapping: Imbox -> Inbox, Feed -> Feed, Paper Trail -> Paper Trail, Jail -> Jail
- This is manually applying what Fastmail rules do at receive time, since rules don't retroactively apply to existing emails

### Screener mailbox
- Screener is a child of Inbox in Fastmail's mailbox hierarchy
- Configurable via env var (default: "Screener")
- All four destination mailboxes (Inbox, Feed, Paper Trail, Jail) must exist at startup -- fail-fast if missing

### Conflict handling
- Same sender with conflicting triage labels (e.g., one email @ToFeed, another @ToImbox): apply @MailroomError to all affected emails, keep triage labels intact, do NOT process
- Sender already exists in a contact group and gets re-triaged to a different group: apply @MailroomError, keep triage label, do NOT process (this should theoretically never happen)
- @MailroomError is a pause signal: emails with this label are skipped on future polls until the user manually removes it

### Error strategy
- @MailroomError is for logical conflicts only (conflicting triage, already-grouped sender)
- Transient failures (network, CardDAV down, API errors): leave triage label in place, retry silently on next poll cycle (per TRIAGE-06)
- No retry counter or escalation for transient failures -- the label stays, the pipeline retries indefinitely

### Sweep scope
- Sweep ALL emails from the sender currently in Screener -- no time limit, no cap
- Screener is a temporary staging area; backlogs should be small
- Sender matching is exact email address only -- no +alias normalization
- Always execute the sweep query, even if only the triggering email exists (consistent behavior, query confirms nothing else is there)

### Claude's Discretion
- Processing order when multiple senders are triaged in one poll cycle
- Internal pipeline architecture (sync vs async, batching strategy)
- Logging granularity within the pipeline steps
- How to resolve the Screener mailbox in the hierarchy (name vs path)

</decisions>

<specifics>
## Specific Ideas

- The pipeline is essentially replicating Fastmail's sieve rules for already-received emails: "if sender is in group X, label as X" -- but applied retroactively to Screener backlog
- Imbox destination adds Inbox label so swept emails appear immediately in the user's inbox (not just archived)
- Feed, Paper Trail, and Jail are effectively archived (no Inbox label) -- they appear in their destination mailbox only

</specifics>

<deferred>
## Deferred Ideas

- **Hierarchical error labels**: Instead of a single @MailroomError, create a hierarchy of sublabels (e.g., @MailroomError/ConflictingTriage, @MailroomError/AlreadyGrouped) to distinguish error types at a glance. Would include auto-creation of labels if they don't exist, conflict resolution for existing labels, and ensuring error labels are hidden from the sidebar. This is a full feature requiring its own design.
- **Alias normalization**: Normalizing +suffixes when matching sender addresses (e.g., treating newsletter+tag@example.com and newsletter@example.com as the same sender). Revisit if the use case arises.

</deferred>

---

*Phase: 03-triage-pipeline*
*Context gathered: 2026-02-24*
