# Architecture

Mailroom is a polling service that triages incoming email in Fastmail. It connects to Fastmail via two protocols -- JMAP for email operations and CardDAV for contact management -- orchestrated by a workflow layer that implements the triage pipeline. The service runs as a single long-lived process, polling on a fixed interval.

## Triage Pipeline

```mermaid
flowchart LR
    A[Fastmail\nScreener] -->|JMAP poll| B[Mailroom\nService]
    B -->|Extract sender| C{Triage\nLabel?}
    C -->|@ToImbox| D[CardDAV:\nAdd to Imbox group]
    C -->|@ToFeed| E[CardDAV:\nAdd to Feed group]
    C -->|@ToPaperTrail| F[CardDAV:\nAdd to Paper Trail group]
    C -->|@ToJail| G[CardDAV:\nAdd to Jail group]
    D & E & F & G -->|JMAP sweep| H[Move emails\nto destination]
```

**How it works:** The user applies a triage label (e.g., `@ToImbox`) to an email in the Screener. On the next poll, Mailroom picks it up, creates or updates the sender's contact in the corresponding CardDAV group, sweeps all of that sender's Screener emails to the destination mailbox, and removes the triage label. Future emails from that sender are auto-routed by Fastmail's contact group rules.

## Components

### ScreenerWorkflow

**File:** `src/mailroom/workflows/screener.py`

The orchestrator. `poll()` is the main entry point, executing one full triage cycle:

1. Collect all triaged emails across all labels, grouped by sender
2. Filter out emails already marked with `@MailroomError`
3. Detect conflicting triage labels (same sender, different labels)
4. Apply `@MailroomError` to conflicted senders
5. Process each clean sender: check already-grouped, upsert contact, sweep emails, remove triage label

Contains business logic only -- no protocol details. Per-sender exceptions are caught to ensure one failing sender doesn't block others (retry on next poll).

### JMAPClient

**File:** `src/mailroom/clients/jmap.py`

Email operations via the JMAP protocol. Handles session discovery (account ID, API URL), mailbox resolution by name, email querying (by mailbox, optionally filtered by sender), batch email moves with chunking (100 emails per request), and label add/remove operations.

### CardDAVClient

**File:** `src/mailroom/clients/carddav.py`

Contact operations via the CardDAV protocol. Handles PROPFIND-based discovery (principal, addressbook home, addressbook URL), contact group validation, email-based contact search via REPORT, contact creation (company or person vCards), merge-cautious upsert (fill empty fields, never overwrite), and group membership management.

### MailroomSettings

**File:** `src/mailroom/core/config.py`

Configuration via pydantic-settings with the `MAILROOM_` prefix. Defines all 18 configurable environment variables with sensible defaults. Provides computed properties for label-to-group mapping, required mailboxes, and contact group lists. See [config.md](config.md) for the full reference.

## Key Design Decisions

- **Triage label removed last:** If any step fails mid-processing, the triage label stays on the email. The next poll picks it up and retries automatically.
- **Error labels are additive:** `@MailroomError` is added without removing the triage label, so the user sees both the original label and the error indicator.
- **Company contacts by default, person contacts via @ToPerson:** The `@ToPerson` label creates a person-type vCard (with parsed first/last name) instead of the default company-type vCard.
- **Merge-cautious:** When upserting contacts, only empty fields are filled. Existing contact data is never overwritten.
- **Per-sender isolation:** A failure processing one sender does not affect other senders in the same poll cycle.

## Planning

This project's planning and roadmap are managed with [GSD](https://github.com/flo/gsd). See `.planning/` for phase history, decisions, and roadmap.
