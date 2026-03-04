# Recover Orphaned Emails from Failed Reset

## Context

This is the Mailroom project — a Fastmail email triage system using JMAP (email) and CardDAV (contacts).

During a previous buggy reset operation, some emails had their only mailbox label removed without being assigned to another mailbox first. This violated RFC 8621 which requires emails to belong to at least one mailbox. Fastmail partially processed the removal, leaving emails in a ghost state — they exist in the database but have empty `mailboxIds`, making them invisible in the Fastmail UI.

The bug has since been fixed (emails are now moved to Screener before label removal), but the orphaned emails from the previous run still exist.

**Known orphaned emails:** At least 2 emails from "Doppler" (the secrets management service). There may be more.

## What You Need to Do

Write a Python script at `.research/recover-corrupted-emails/find_and_recover.py` that:

1. **Authenticates with Fastmail JMAP** — use the existing auth pattern from this project. Check `src/mailroom/clients/jmap.py` for the JMAP client implementation and `src/mailroom/core/config.py` for how credentials are loaded (MAILROOM_JMAP_TOKEN env var, MAILROOM_JMAP_HOST).

2. **Finds orphaned emails** — Query for emails that have empty or missing `mailboxIds`. Try:
   - `Email/query` with a filter that finds emails not in any known mailbox
   - Or `Email/get` scanning for emails where `mailboxIds` is empty
   - The JMAP spec says `mailboxIds` must be non-empty, so Fastmail might have a special way to surface these. Check if searching with no mailbox filter returns them.
   - Another approach: search by sender "Doppler" across all mailboxes and see what comes back vs what's actually visible.

3. **Reports what it finds** — Print each orphaned email's subject, sender, date, and current `mailboxIds` state.

4. **Recovers them** — Move orphaned emails to the Screener mailbox by setting `mailboxIds: { "<screener_mailbox_id>": true }`. Include a `--dry-run` flag (default) and `--apply` flag to actually fix them.

## Reference Files

- `src/mailroom/clients/jmap.py` — JMAP client with auth, session handling, `Email/query`, `Email/get`, `Email/set` methods
- `src/mailroom/core/config.py` — Config loading, env vars
- `human-tests/test_1_auth.py` — Simple auth test showing how to connect
- `human-tests/test_2_query.py` — Example of querying emails

## Important

- This is a research/recovery script, not production code
- Keep it standalone (can import from mailroom but should also work with direct JMAP calls)
- Default to dry-run, require explicit --apply
- Print everything you find — we want to understand the full scope of damage
