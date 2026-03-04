# Resolution: Orphaned Emails from Failed Reset

## Date: 2026-03-04

## What Happened

During the first UAT run of Phase 14, `mailroom reset --apply` hit a bug:
Step 1 called `batch_remove_labels()` on emails in Feed, Jail, and Paper Trail
without first moving them to Screener. Since those emails only had one mailbox
(no `add_to_inbox`), removing it would leave them with empty `mailboxIds`,
violating RFC 8621.

Fastmail returned "unknown error" for the affected emails. The reset aborted
partway through.

**Bug fix:** commit `afa230a` — Step 1 now calls `batch_add_labels(screener_mb_id)`
before `batch_remove_labels`, ensuring emails always have at least one mailbox.

## Investigation

We wrote `find_and_recover.py` to find orphaned emails via JMAP:

1. **Sender-based search** (`from: "doppler"`, `text: "doppler"`) — found 0 results
2. **Broad temporal scan** (all emails in last 30 days) — found 0 orphans
3. **Set-difference** (all 26,410 email IDs vs union of per-mailbox IDs) — exact match, 0 orphans

**Conclusion:** Fastmail's JMAP server correctly **rejected** the invalid removals.
The `notUpdated` response meant the emails' mailbox state was never changed — they
stayed in their original mailboxes. The 2 missing Doppler emails were likely deleted
through normal means (Trash emptied, etc.), not by the reset bug.

## How The Emails Were Actually Recovered

The missing emails were recovered using **Fastmail's built-in restore feature**:

1. Log into Fastmail web UI (https://www.fastmail.com)
2. Go to **Settings** (gear icon)
3. Navigate to **Privacy & Security**
4. Find **"Restore deleted drafts and messages"**
5. Click it — Fastmail restores soft-deleted emails from their internal retention

Fastmail soft-deletes messages rather than hard-deleting them, so even permanently
deleted emails can be recovered for some retention period through this feature.
This restored the missing Doppler emails (and potentially others) without needing
any JMAP-level intervention.

## Key Learnings

- **Fastmail enforces RFC 8621** — it rejects `Email/set` operations that would
  leave `mailboxIds` empty, returning `notUpdated` errors. This prevented data loss.
- **JMAP queries cannot find truly orphaned emails** — if an email somehow ended up
  with empty `mailboxIds`, it would be invisible to `Email/query` (even filterless
  queries). The set-difference approach is the best programmatic detection method.
- **Fastmail's "Restore deleted messages" is the nuclear recovery option** — it
  operates below the JMAP layer and can recover emails that are invisible to the API.
- **Phone/desktop showing different state** = stale cache, not ghost emails. The web
  UI is the source of truth for server state.
