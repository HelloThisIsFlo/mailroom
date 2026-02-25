# Phase 3: Triage Pipeline - Research

**Researched:** 2026-02-24
**Domain:** Workflow orchestration, polling pipeline, idempotent multi-step processing, conflict detection
**Confidence:** HIGH

## Summary

Phase 3 wires the JMAP and CardDAV clients (built in Phases 1 and 2) into the end-to-end screener triage workflow. This is the core business logic of Mailroom: poll for triage labels, group senders by label, detect conflicts, upsert contacts into groups, sweep all Screener emails to destinations, and clean up triage labels -- all with retry safety on transient failures.

The technical risk is low. Both clients are proven against live Fastmail (Phase 2 validation gate passed). The pipeline is pure orchestration: it calls existing methods in a defined sequence. The challenge is correctness, not protocol integration. The three critical correctness properties are: (1) conflict detection before any mutations (conflicting triage labels on same sender, already-grouped sender re-triaged), (2) idempotent processing so retries are safe (re-processing the same email must not create duplicate contacts or moves), and (3) label-as-state for retry safety (the triage label stays on until the entire pipeline succeeds for that sender).

The existing codebase provides all the building blocks: `JMAPClient.query_emails()`, `JMAPClient.get_email_senders()`, `JMAPClient.batch_move_emails()`, `JMAPClient.remove_label()` for email operations; `CardDAVClient.upsert_contact()`, `CardDAVClient.add_to_group()`, `CardDAVClient.validate_groups()` for contact operations; and `MailroomSettings` with `label_to_group_mapping`, `triage_labels`, and `contact_groups` for configuration. The workflow module (`src/mailroom/workflows/`) exists as an empty placeholder ready for `screener.py`.

**Primary recommendation:** Build a `ScreenerWorkflow` class in `src/mailroom/workflows/screener.py` that takes both clients and config as constructor arguments. The workflow's `process_triage_batch()` method handles one poll cycle: query all triage labels, group emails by sender, detect conflicts, then process each clean sender sequentially. Each sender processing is wrapped in try/except -- transient failures leave the triage label for retry; logical conflicts apply @MailroomError. No new dependencies needed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Every swept email gets: Screener label removed + destination label added
- The triggering email (has both Screener + action label) gets both labels removed, destination label added
- Other emails from same sender in Screener (Screener label only) get Screener removed, destination label added
- Destination label mapping: Imbox -> Inbox, Feed -> Feed, Paper Trail -> Paper Trail, Jail -> Jail
- This is manually applying what Fastmail rules do at receive time, since rules don't retroactively apply to existing emails
- Screener is a child of Inbox in Fastmail's mailbox hierarchy
- Configurable via env var (default: "Screener")
- All four destination mailboxes (Inbox, Feed, Paper Trail, Jail) must exist at startup -- fail-fast if missing
- Same sender with conflicting triage labels (e.g., one email @ToFeed, another @ToImbox): apply @MailroomError to all affected emails, keep triage labels intact, do NOT process
- Sender already exists in a contact group and gets re-triaged to a different group: apply @MailroomError, keep triage label, do NOT process (this should theoretically never happen)
- @MailroomError is a pause signal: emails with this label are skipped on future polls until the user manually removes it
- @MailroomError is for logical conflicts only (conflicting triage, already-grouped sender)
- Transient failures (network, CardDAV down, API errors): leave triage label in place, retry silently on next poll cycle (per TRIAGE-06)
- No retry counter or escalation for transient failures -- the label stays, the pipeline retries indefinitely
- Sweep ALL emails from the sender currently in Screener -- no time limit, no cap
- Screener is a temporary staging area; backlogs should be small
- Sender matching is exact email address only -- no +alias normalization
- Always execute the sweep query, even if only the triggering email exists (consistent behavior, query confirms nothing else is there)

### Claude's Discretion
- Processing order when multiple senders are triaged in one poll cycle
- Internal pipeline architecture (sync vs async, batching strategy)
- Logging granularity within the pipeline steps
- How to resolve the Screener mailbox in the hierarchy (name vs path)

### Deferred Ideas (OUT OF SCOPE)
- **Hierarchical error labels**: Instead of a single @MailroomError, create a hierarchy of sublabels (e.g., @MailroomError/ConflictingTriage, @MailroomError/AlreadyGrouped). Full feature requiring own design.
- **Alias normalization**: Normalizing +suffixes when matching sender addresses. Revisit if the use case arises.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRIAGE-01 | Service polls for emails with triage labels every 5 minutes (configurable) | `MailroomSettings.poll_interval` already exists (default 300s). `MailroomSettings.triage_labels` returns all four label names. `JMAPClient.query_emails(mailbox_id)` queries one label at a time. The workflow's `poll()` method iterates all triage labels and collects results. Polling loop itself is Phase 4 (this phase builds the workflow that the loop calls). |
| TRIAGE-02 | For each triaged email: extract sender, create/update contact, assign to group, remove triage label | `JMAPClient.get_email_senders(email_ids)` extracts sender addresses. `CardDAVClient.upsert_contact(email, display_name, group_name)` handles create-or-update with group assignment. `JMAPClient.remove_label(email_id, mailbox_id)` removes the triage label. Workflow orchestrates these in sequence per sender. |
| TRIAGE-03 | After contact assignment, sweep all Screener emails from that sender to the correct destination | `JMAPClient.query_emails(screener_id, sender=email)` finds all sender's emails in Screener. `JMAPClient.batch_move_emails(email_ids, remove_mailbox_id=screener_id, add_mailbox_ids=[dest_id])` moves them. Caller assembles `add_mailbox_ids` list based on destination. |
| TRIAGE-04 | For Imbox triage: swept emails get Inbox label re-added so they appear immediately | When destination is Imbox, `add_mailbox_ids` includes both the Imbox mailbox ID and the Inbox mailbox ID. `JMAPClient.batch_move_emails()` already supports multiple add IDs (proven in Phase 1 tests). |
| TRIAGE-05 | Processing is idempotent -- re-processing the same email does not create duplicate contacts | `CardDAVClient.upsert_contact()` searches by email before creating (returns "existing" if found). `CardDAVClient.add_to_group()` is idempotent (skips PUT if already a member). `JMAPClient.batch_move_emails()` adds labels that may already exist (JMAP patch is idempotent: setting `mailboxIds/x: true` when already true is a no-op). |
| TRIAGE-06 | If CardDAV fails, triage label is left in place for retry on next poll cycle | Workflow wraps each sender's processing in try/except. On transient error (httpx exceptions, HTTP 5xx), the triage label is never removed (remove_label is the last step). On next poll cycle, the same email still has the triage label and will be re-processed. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.28.x (existing) | HTTP client for both JMAP and CardDAV | Already in use. No changes needed. |
| structlog | 25.x (existing) | Structured logging throughout the pipeline | Already configured from Phase 1. Bind context per sender/operation. |
| pydantic-settings | 2.x (existing) | Configuration for Screener mailbox name, destination mapping | Already in use. Needs minor addition for screener_mailbox config. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| vobject | 1.0.0 (existing) | vCard operations via CardDAV client | Already in use, no direct use in workflow -- called via CardDAVClient. |
| pytest | latest (existing) | Test framework | Test the workflow with mocked clients. |
| pytest-httpx | latest (existing) | Mock HTTP calls | May be used indirectly; most workflow tests mock at client level. |

### Alternatives Considered
| Instead of | Could Use | Why Not |
|------------|-----------|---------|
| Synchronous sequential processing | asyncio with concurrent sender processing | Single-user service, 5-minute poll interval. Async adds complexity with zero benefit. Both clients are synchronous. Sequential processing is simpler and safer (no concurrent group modifications). |
| Simple try/except error handling | Retry library (tenacity) | Transient failures are handled by the poll cycle itself -- leave label, retry next time. No need for in-process retry logic. The poll loop IS the retry mechanism. |

**Installation:**
```bash
# No new dependencies needed. All required libraries already installed.
```

## Architecture Patterns

### Recommended Project Structure
```
src/mailroom/
├── clients/
│   ├── __init__.py
│   ├── jmap.py              # Existing (Phase 1)
│   └── carddav.py           # Existing (Phase 2)
├── core/
│   ├── __init__.py
│   ├── config.py             # MODIFIED: add screener_mailbox, destination_mailboxes
│   └── logging.py            # Existing, unchanged
└── workflows/
    ├── __init__.py            # MODIFIED: update docstring
    └── screener.py            # NEW: ScreenerWorkflow class
tests/
├── conftest.py                # MODIFIED: add shared workflow fixtures
├── test_config.py             # MODIFIED: test new config properties
├── test_screener_workflow.py  # NEW: workflow unit tests with mocked clients
├── test_jmap_client.py        # Existing, unchanged
├── test_carddav_client.py     # Existing, unchanged
└── test_logging.py            # Existing, unchanged
```

### Pattern 1: Workflow as Orchestrator (No Protocol Logic)
**What:** The `ScreenerWorkflow` class calls existing client methods in sequence. It contains business logic (conflict detection, destination mapping, ordering) but zero protocol details (no HTTP calls, no XML, no vCard).
**When to use:** Always. This is the phase's primary architectural pattern.
**Example:**
```python
# Source: Established pattern from .planning/research/ARCHITECTURE.md
import structlog

class ScreenerWorkflow:
    """Orchestrates the screener triage pipeline.

    Calls JMAPClient and CardDAVClient methods in sequence.
    Contains business logic only -- no protocol details.
    """

    def __init__(
        self,
        jmap: JMAPClient,
        carddav: CardDAVClient,
        settings: MailroomSettings,
        mailbox_ids: dict[str, str],  # resolved at startup
    ) -> None:
        self._jmap = jmap
        self._carddav = carddav
        self._settings = settings
        self._mailbox_ids = mailbox_ids
        self._log = structlog.get_logger(component="screener")
```

### Pattern 2: Group-by-Sender Before Processing
**What:** Query all triage labels, extract senders, group emails by (sender, label), then detect conflicts BEFORE any mutations. Process only conflict-free senders.
**When to use:** Every poll cycle. The grouping step ensures conflict detection catches all issues before any contact/email changes.
**Example:**
```python
def poll(self) -> int:
    """Execute one poll cycle. Returns count of senders processed."""
    # Step 1: Collect all triaged emails across all labels
    triaged: dict[str, list[tuple[str, str]]] = {}  # sender -> [(email_id, label)]
    for label_name in self._settings.triage_labels:
        label_id = self._mailbox_ids[label_name]
        email_ids = self._jmap.query_emails(label_id)
        if not email_ids:
            continue
        senders = self._jmap.get_email_senders(email_ids)
        for email_id, sender in senders.items():
            triaged.setdefault(sender, []).append((email_id, label_name))

    if not triaged:
        self._log.debug("poll_complete", triaged_senders=0)
        return 0

    # Step 2: Detect conflicts
    clean, conflicted = self._detect_conflicts(triaged)

    # Step 3: Apply @MailroomError to conflicted senders
    for sender, emails in conflicted.items():
        self._apply_error_label(sender, emails)

    # Step 4: Process clean senders
    processed = 0
    for sender, emails in clean.items():
        try:
            self._process_sender(sender, emails)
            processed += 1
        except Exception:
            self._log.exception("sender_failed", sender=sender)
            # Leave triage labels in place for retry

    return processed
```

### Pattern 3: Conflict Detection (Pre-Mutation Gate)
**What:** Before any mutations, check for two conflict types: (a) same sender with different triage labels in one poll, (b) sender already exists in a contact group.
**When to use:** Every poll cycle, after collecting triaged emails, before processing any sender.
**Example:**
```python
def _detect_conflicts(
    self,
    triaged: dict[str, list[tuple[str, str]]],
) -> tuple[dict, dict]:
    """Split senders into clean and conflicted.

    Conflict type 1: Same sender has emails with different triage labels.
    Conflict type 2: Sender already exists in a contact group (checked
                     via CardDAV during processing, not here).

    Returns (clean_senders, conflicted_senders).
    """
    clean = {}
    conflicted = {}

    for sender, emails in triaged.items():
        labels = {label for _, label in emails}
        if len(labels) > 1:
            # Conflicting triage labels
            conflicted[sender] = emails
        else:
            clean[sender] = emails

    return clean, conflicted
```

### Pattern 4: Destination Mapping (Label -> Mailbox + Group)
**What:** Map each triage label to its destination mailbox ID(s) and contact group name. The Imbox destination is special: it adds both the destination mailbox ID and the Inbox ID.
**When to use:** When building the batch_move_emails call for each sender.
**Example:**
```python
# The config already has label_to_group_mapping.
# The pipeline needs to extend this to include mailbox IDs.

# Destination mapping:
# @ToImbox  -> group: "Imbox",  mailbox: "Inbox",       also_add: ["Inbox"] (Inbox label)
# @ToFeed   -> group: "Feed",   mailbox: "Feed",        also_add: []
# @ToPaper  -> group: "Paper Trail", mailbox: "Paper Trail", also_add: []
# @ToJail   -> group: "Jail",   mailbox: "Jail",        also_add: []
#
# NOTE: "Imbox" is a contact GROUP name, not a mailbox.
# The actual DESTINATION MAILBOX is "Inbox" for Imbox destination.
# Feed, Paper Trail, and Jail are both group names AND mailbox names.
#
# For Imbox: batch_move_emails(ids, screener_id, [inbox_id])
#   - Removes Screener label, adds Inbox label
#   - Emails appear in Inbox immediately
#
# For Feed/Paper Trail/Jail: batch_move_emails(ids, screener_id, [dest_id])
#   - Removes Screener label, adds destination label
#   - Emails appear only in their destination mailbox (archived)
```

### Pattern 5: Triage Label as State Machine
**What:** The triage label serves double duty: it's the user's triage instruction AND the pipeline's state marker. The label is removed only as the LAST step, after all other operations succeed. This makes the pipeline naturally retry-safe.
**When to use:** Always. The remove-label-last pattern is the core of TRIAGE-06.
**Example:**
```python
def _process_sender(
    self, sender: str, emails: list[tuple[str, str]]
) -> None:
    """Process a single sender's triage.

    Steps execute in order. If any step fails, the exception
    propagates and the triage label is NOT removed (retry on next poll).
    """
    label_name = emails[0][1]  # All emails have the same label (conflict-free)
    email_ids = [eid for eid, _ in emails]
    group_name = self._settings.label_to_group_mapping[label_name]["group"]

    log = self._log.bind(sender=sender, label=label_name, group=group_name)

    # 1. Upsert contact into group (CardDAV)
    result = self._carddav.upsert_contact(sender, None, group_name)
    log.info("contact_upserted", action=result["action"], uid=result["uid"])

    # 2. Sweep all Screener emails from this sender (JMAP)
    screener_id = self._mailbox_ids["Screener"]
    sender_emails = self._jmap.query_emails(screener_id, sender=sender)

    if sender_emails:
        add_ids = self._get_destination_mailbox_ids(label_name)
        self._jmap.batch_move_emails(sender_emails, screener_id, add_ids)
        log.info("emails_swept", count=len(sender_emails))

    # 3. Remove triage label from triggering email(s) -- LAST STEP
    label_id = self._mailbox_ids[label_name]
    for email_id in email_ids:
        self._jmap.remove_label(email_id, label_id)

    log.info("triage_complete", emails_moved=len(sender_emails))
```

### Pattern 6: Error Label Application
**What:** Apply the @MailroomError label to emails that have logical conflicts. The error label is additive -- it does not remove the triage label.
**When to use:** When a sender has conflicting triage labels, or when a sender is already in a contact group and gets re-triaged.
**Example:**
```python
def _apply_error_label(
    self, sender: str, emails: list[tuple[str, str]]
) -> None:
    """Apply @MailroomError to all emails for a conflicted sender.

    Keeps triage labels intact. The @MailroomError label is a signal
    to the user to resolve the conflict manually.
    """
    error_id = self._mailbox_ids[self._settings.label_mailroom_error]
    email_ids = [eid for eid, _ in emails]

    # Add error label to all affected emails
    # Uses batch Email/set with patch syntax (add only, no remove)
    for email_id in email_ids:
        # Use JMAP patch to add the error label
        self._jmap.call([
            ["Email/set", {
                "accountId": self._jmap.account_id,
                "update": {
                    email_id: {f"mailboxIds/{error_id}": True}
                },
            }, "err0"]
        ])

    labels = {label for _, label in emails}
    self._log.warning(
        "conflict_detected",
        sender=sender,
        labels=sorted(labels),
        affected_emails=len(email_ids),
    )
```

### Anti-Patterns to Avoid
- **Processing before conflict check:** Never upsert a contact or move emails before checking for conflicting triage labels. Once a contact is in a group, undoing it is hard.
- **Removing triage label early:** The triage label must be the LAST thing removed. If CardDAV fails after label removal, the retry mechanism is broken -- the email no longer appears in triage queries.
- **Catching exceptions too broadly in the per-sender loop:** Catch `Exception` for the retry boundary, but let `KeyboardInterrupt` and `SystemExit` propagate. Do not catch `BaseException`.
- **Using async processing for senders:** Sequential processing within a poll cycle is safer (no concurrent group modifications to the same CardDAV group vCard) and simpler. The 5-minute poll interval provides ample time.
- **Adding @MailroomError via batch_move_emails:** The error label should be ADDED without removing any existing labels. `batch_move_emails` removes a source label. Use direct `Email/set` with patch syntax to add only.
- **Querying for already-grouped sender in the pre-mutation gate:** The "already-grouped" check requires a CardDAV search for each sender -- expensive and prone to transient failures. Defer this check to the per-sender processing step where CardDAV errors are already handled by the retry mechanism.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Contact upsert with duplicate prevention | Custom search-then-create with race conditions | `CardDAVClient.upsert_contact()` | Already built and tested in Phase 2. Handles search, create, merge-cautious update, and group add in one call. |
| Email batch moving with chunking | Custom loop building JMAP patches | `JMAPClient.batch_move_emails()` | Already built and tested in Phase 1. Handles chunking at 100 emails, error reporting, patch syntax. |
| Triage label removal | Direct JMAP calls in workflow | `JMAPClient.remove_label()` | Already built and tested in Phase 1. Handles patch syntax and error checking. |
| Retry logic for transient failures | In-process retry with backoff/tenacity | Poll cycle as retry | The polling loop IS the retry mechanism. Leave the label, let the next poll cycle handle it. Zero additional code. |
| Configuration validation | Custom startup checks | `MailroomSettings` + `JMAPClient.resolve_mailboxes()` + `CardDAVClient.validate_groups()` | Already built. Startup validation catches missing mailboxes and groups before processing. |

**Key insight:** Phase 3 writes almost no protocol code. The workflow is pure orchestration of existing, tested client methods. The complexity is in the business logic: conflict detection, destination mapping, error labeling, and ensuring the processing order guarantees retry safety.

## Common Pitfalls

### Pitfall 1: Destination Mailbox vs Contact Group Name Confusion
**What goes wrong:** The code uses the contact group name "Imbox" as a mailbox name, but the actual destination mailbox is "Inbox" (for Imbox) or "Feed"/"Paper Trail"/"Jail" (for the others).
**Why it happens:** The config's `label_to_group_mapping` stores group names, not destination mailbox names. The Imbox group routes emails to the Inbox mailbox (plus Inbox label for visibility).
**How to avoid:** Build an explicit destination map at startup that maps each triage label to: (a) the contact group name, (b) the list of mailbox IDs to add. For Imbox, the add list is `[inbox_id]`. For Feed/Paper Trail/Jail, the add list is `[feed_id]` / `[paper_trail_id]` / `[jail_id]`.
**Warning signs:** Emails moved to wrong mailbox, or "Imbox" mailbox not found error at startup.

### Pitfall 2: Triage Label Removal Order
**What goes wrong:** The triage label is removed before the sweep completes. If the sweep fails (network error), the triage label is gone and the email will not be retried on the next poll.
**Why it happens:** Natural code order puts "clean up" before "heavy operation." But in this pipeline, the triage label IS the retry marker.
**How to avoid:** Enforce a strict step order: (1) upsert contact, (2) sweep emails, (3) remove triage label. Step 3 is always last. Never reorder.
**Warning signs:** Emails stuck with no triage label but sender not in group, or emails remaining in Screener after triage.

### Pitfall 3: @MailroomError Skip Logic
**What goes wrong:** Emails already marked with @MailroomError are re-processed on every poll cycle, wasting API calls and potentially causing cascading errors.
**Why it happens:** The poll query finds all emails with triage labels -- it does not exclude emails that also have @MailroomError.
**How to avoid:** After querying triage labels, filter out any email that also has the @MailroomError label. This can be done by querying the email's mailbox IDs (using `Email/get` with `properties: ["mailboxIds"]`) and checking if the error label's mailbox ID is present. Alternatively, check after collecting emails -- get mailbox IDs for all triaged emails and exclude those with @MailroomError.
**Warning signs:** Log messages showing the same conflicted sender being processed every poll cycle.

### Pitfall 4: Conflicting Labels Across Multiple Emails from Same Sender
**What goes wrong:** Sender has 3 emails: one labeled @ToImbox, one labeled @ToFeed, one with no triage label. The pipeline processes the @ToImbox email first, moves all sender's Screener emails to Inbox, then encounters the @ToFeed email for the same sender (now with no emails left in Screener).
**Why it happens:** Processing labels independently without first grouping by sender.
**How to avoid:** Group ALL triaged emails by sender FIRST, then check for conflicting labels per sender, then process only conflict-free senders.
**Warning signs:** Same sender's emails split across destinations, or @MailroomError applied after some emails already moved.

### Pitfall 5: Already-Grouped Sender Detection Timing
**What goes wrong:** Checking if a sender is already in a contact group during the conflict detection phase requires a CardDAV search for every sender. If CardDAV is down, the entire poll cycle fails.
**Why it happens:** Overly eager pre-validation.
**How to avoid:** Check for "already in a different group" during the per-sender processing step, where transient CardDAV failures are already handled by the retry mechanism. The upsert_contact call can detect this condition.
**Warning signs:** Entire poll cycle failing because of a CardDAV timeout during pre-validation.

### Pitfall 6: Emails Without Valid Senders
**What goes wrong:** Some emails may have empty or missing "From" headers. `get_email_senders()` returns a dict that may not include all requested email IDs.
**Why it happens:** Malformed emails, system-generated messages, or edge cases in email headers.
**How to avoid:** After calling `get_email_senders()`, check which email IDs got results. For emails without senders, log a warning and skip (do not remove the triage label -- let the user handle it manually, or apply @MailroomError).
**Warning signs:** KeyError when accessing sender for an email ID, or silent skipping of emails.

## Code Examples

Verified patterns using existing codebase methods:

### Startup Validation: Resolve All Required Mailboxes
```python
# All mailboxes needed by the pipeline, resolved at startup
required_mailboxes = [
    "Inbox",          # For Imbox destination (re-label)
    "Screener",       # Source mailbox for sweep
    "Feed",           # Destination mailbox
    "Paper Trail",    # Destination mailbox
    "Jail",           # Destination mailbox
    *settings.triage_labels,     # @ToImbox, @ToFeed, @ToPaperTrail, @ToJail
    settings.label_mailroom_error,  # @MailroomError
]

mailbox_ids = jmap.resolve_mailboxes(required_mailboxes)
# Returns: {"Inbox": "mb-001", "Screener": "mb-002", "@ToImbox": "mb-003", ...}
```

### Destination Mailbox ID Resolution
```python
# Build destination map from config + resolved mailbox IDs
# For each triage label -> list of mailbox IDs to add during sweep

def _get_destination_mailbox_ids(self, label_name: str) -> list[str]:
    """Return the mailbox IDs to add when sweeping for this label's destination.

    Imbox: [inbox_id] -- emails appear in Inbox
    Feed/Paper Trail/Jail: [destination_id] -- emails go to their mailbox
    """
    mapping = self._settings.label_to_group_mapping[label_name]
    destination = mapping["destination"]

    if destination == self._settings.group_imbox:
        # Imbox destination: add Inbox label (emails appear in Inbox)
        return [self._mailbox_ids["Inbox"]]
    else:
        # Feed/Paper Trail/Jail: add the destination mailbox label
        return [self._mailbox_ids[destination]]
```

### Adding @MailroomError Label (Patch Syntax -- Add Only)
```python
# Add @MailroomError without removing any existing labels
# This is different from batch_move_emails which removes a source label
error_id = mailbox_ids["@MailroomError"]

# JMAPClient.call() is already available for custom JMAP operations
jmap.call([
    ["Email/set", {
        "accountId": jmap.account_id,
        "update": {
            email_id: {f"mailboxIds/{error_id}": True}
        },
    }, "err0"]
])
```

### @MailroomError Filtering (Skip Already-Errored Emails)
```python
# After querying triaged emails, filter out those with @MailroomError
# Use Email/get to check mailboxIds for each triaged email
error_id = mailbox_ids["@MailroomError"]

# Get mailbox membership for all triaged email IDs
responses = jmap.call([
    ["Email/get", {
        "accountId": jmap.account_id,
        "ids": all_triaged_email_ids,
        "properties": ["id", "mailboxIds"],
    }, "g0"]
])
email_list = responses[0][1]["list"]

# Filter out emails that have @MailroomError
clean_ids = [
    e["id"] for e in email_list
    if error_id not in e.get("mailboxIds", {})
]
```

### Structured Logging for Pipeline Operations
```python
# Source: existing structlog patterns from Phase 1
import structlog

log = structlog.get_logger(component="screener")

# Poll cycle summary (debug level -- silent when nothing to do)
log.debug("poll_complete", triaged_senders=0)

# Processing summary (info level -- only when work is done)
log.info("poll_complete", triaged_senders=3, processed=2, conflicts=1)

# Per-sender context binding
sender_log = log.bind(sender="alice@example.com", label="@ToImbox", group="Imbox")
sender_log.info("contact_upserted", action="created", uid="abc-123")
sender_log.info("emails_swept", count=5, destination="Inbox")
sender_log.info("triage_complete")

# Conflict warning
log.warning("conflict_detected", sender="bob@example.com",
            labels=["@ToFeed", "@ToImbox"], affected_emails=3)

# Transient failure (caught and retried)
log.warning("sender_failed", sender="carol@example.com",
            error="ConnectionError", retry="next_poll")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Complex state machines for pipeline steps | Labels-as-state with remove-last pattern | N/A (project design) | Zero persistence needed, natural retry, no state database |
| In-process retry with backoff libraries | Poll cycle as retry mechanism | N/A (project design) | Simpler code, same result, relies on polling interval for "backoff" |
| Separate error queues/dead-letter patterns | @MailroomError label as user-visible pause | N/A (project design) | Error state visible in Fastmail UI, user can resolve without accessing service |

**Deprecated/outdated:**
- None specific to this phase -- it's pure application logic using established patterns.

## Open Questions

1. **Should Screener mailbox config use name or hierarchical path?**
   - What we know: CONTEXT says Screener is a child of Inbox in Fastmail's mailbox hierarchy. `resolve_mailboxes()` matches by name with top-level preference.
   - What's unclear: If "Screener" exists as both a child of Inbox and a top-level mailbox, the resolver would pick the top-level one. Is this the correct behavior for this use case?
   - Recommendation: Use the name "Screener" with the existing resolver. The resolver already prefers top-level (parentId=None). If Screener is a child of Inbox, it will still be found by name (just not preferred if a top-level duplicate exists). In practice, there will only be one "Screener" mailbox. Add a `screener_mailbox` config setting with default "Screener". **Confidence: HIGH** -- the existing resolver handles this correctly in the expected single-Screener scenario.

2. **How to detect "sender already in a different group" during processing?**
   - What we know: The CONTEXT says to apply @MailroomError when a sender is already in a contact group and gets re-triaged to a different group. `CardDAVClient.upsert_contact()` currently adds to the specified group without checking other groups.
   - What's unclear: The current `upsert_contact()` method does not check if the contact is already a member of a different group.
   - Recommendation: Add a check in the workflow (not in CardDAVClient) before calling `upsert_contact()`. Query all group vCards (already loaded during `validate_groups()` at startup) for the contact's UID. If found in a different group than the target, apply @MailroomError. This can be done via CardDAVClient by checking group membership or by adding a `check_group_membership(contact_uid)` method. **Confidence: MEDIUM** -- the check adds CardDAV overhead but is necessary per user decision.

3. **@MailroomError filtering: query-time vs post-query?**
   - What we know: JMAP Email/query supports `filter: { inMailbox: labelId }` but does not natively support "NOT in mailbox X" as a filter.
   - What's unclear: Whether JMAP's `FilterOperator` with `NOT` condition can exclude emails by mailbox.
   - Recommendation: Filter post-query. After collecting triaged email IDs, use `Email/get` with `properties: ["id", "mailboxIds"]` to check for @MailroomError presence. Exclude those IDs before processing. This adds one JMAP call per poll cycle but is simple and reliable. **Confidence: HIGH** -- post-query filtering is straightforward.

4. **Config: should `label_to_group_mapping` also include destination mailbox name?**
   - What we know: Current mapping has `{label -> {group, destination}}` where destination equals group name. But "Imbox" is a group name, not a mailbox name -- the destination mailbox is "Inbox".
   - What's unclear: Whether to modify the config mapping or handle the Imbox special case in the workflow.
   - Recommendation: Add a `destination_mailbox` field to the mapping that contains the actual Fastmail mailbox name. For Imbox, this is "Inbox". For others, it matches the group name. This makes the mapping self-contained and the workflow does not need special-case logic. **Confidence: HIGH** -- clean separation.

## Sources

### Primary (HIGH confidence)
- **Existing codebase** (`src/mailroom/`) -- All client methods verified via unit tests and Phase 2 live validation. Method signatures, return types, and error handling directly inspected.
- **JMAP Specification (RFC 8620/8621)** -- Email/set patch syntax for label addition/removal, Email/query filter semantics.
- **Phase 1 Research** (`.planning/phases/01-foundation-and-jmap-client/01-RESEARCH.md`) -- JMAP patterns, batch operations, pagination.
- **Phase 2 Research** (`.planning/phases/02-carddav-client-validation-gate/02-RESEARCH.md`) -- CardDAV upsert, group membership, ETag handling.
- **Architecture Research** (`.planning/research/ARCHITECTURE.md`) -- Workflow-as-orchestrator pattern, data flow, poll cycle design.

### Secondary (MEDIUM confidence)
- **03-CONTEXT.md** -- User decisions on conflict handling, sweep scope, error strategy. Authoritative for business logic.

### Tertiary (LOW confidence)
- **JMAP NOT filter support** -- Unclear whether Fastmail implements FilterOperator with NOT condition for mailbox exclusion. Post-query filtering recommended as safer approach.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- No new dependencies. All libraries already proven in Phases 1 and 2.
- Architecture: HIGH -- Workflow-as-orchestrator is the established project pattern. All client APIs are known and tested.
- Pitfalls: HIGH -- Pitfalls are business logic concerns (ordering, conflicts, idempotency) rather than protocol unknowns. All can be tested with mocked clients.
- Conflict detection: MEDIUM -- The "already-grouped sender" check requires CardDAV group membership inspection, which adds complexity. Needs careful implementation.

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (stable domain, 30 days)
