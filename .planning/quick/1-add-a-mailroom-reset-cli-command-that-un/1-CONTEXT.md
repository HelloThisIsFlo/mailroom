# Quick Task 1: Add mailroom reset CLI command - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Task Boundary

Add a `reset` CLI command (alongside existing `setup` and `run`) that undoes all mailroom changes: cleans contacts, removes managed labels from emails, empties contact groups. Follows the same dry-run/apply pattern as the setup command.

</domain>

<decisions>
## Implementation Decisions

### Contact Handling
- **Never auto-delete** contacts — cannot reliably distinguish "created by mailroom" vs "pre-existing with empty note"
- Strip the `— Mailroom —` NOTE section from all annotated contacts
- Remove annotated contacts from all managed contact groups
- Print all cleaned contacts in the report
- **Flag likely-created contacts separately**: contacts where (a) only group memberships are mailroom-managed groups, (b) note is ONLY the mailroom section (no pre-existing note content), (c) FN matches mailroom's name extraction pattern. These are listed separately for easier manual deletion

### Email Label Scope
- Remove ALL managed labels from all affected emails (triage labels like @ToImbox, destination labels like Feed, error/warning labels)
- Do NOT touch the Screener mailbox/label — leave it intact
- In Fastmail, labels = mailboxes, so searching by label name finds all affected emails

### Resource Deletion
- **Keep all resources in place** (mailboxes, labels, contact groups) — do NOT delete them
- Only empty their contents (remove label assignments from emails, remove members from groups)
- User can re-run `setup` after reset to verify everything is clean, then restart the service

### CLI Pattern
- Follow the existing `setup` command's dry-run/apply pattern (provisioner.py)
- `python -m mailroom reset` = dry-run (show what would be cleaned)
- `python -m mailroom reset --apply` = execute the cleanup
- Report format similar to setup's resource table

</decisions>

<specifics>
## Specific Ideas

- Dry-run output should clearly show counts: N contacts to clean, N emails to un-label, N group memberships to remove
- Likely-created contacts flagged with a distinct marker in the report
- Operation order for apply: (1) remove labels from emails, (2) remove contacts from groups, (3) strip mailroom NOTE from contacts
- Triage label removal is last step in normal workflow for retry safety — reset can be more aggressive since it's a one-off

</specifics>
