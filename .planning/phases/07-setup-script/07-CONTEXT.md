# Phase 7: Setup Script - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Idempotent CLI command that provisions all required Fastmail resources (mailboxes, action labels, contact groups) for the user's configured triage categories, with dry-run safety and sieve rule guidance. Reads the same `MAILROOM_TRIAGE_CATEGORIES` config as the main service.

</domain>

<decisions>
## Implementation Decisions

### Output & reporting
- Summary table with indented tree showing mailbox hierarchy (parent `Triage/` with child mailboxes)
- Three resource groups displayed separately: **Mailboxes** (with hierarchy), **Action Labels** (triage labels like "to Feed"), **Contact Groups** (like "Imbox", "Feed")
- Statuses: `✓ exists`, `+ create` (dry-run), `✓ created` (apply), `✗ FAILED` (apply failure)
- Live progress during `--apply` — each resource reported as it's processed
- Summary line at bottom: `N created · N existing` (or `N to create · N existing` for dry-run)
- Inline error reasons for failures (e.g., `403 Forbidden: insufficient permissions`)

### Sieve rule guidance
- Read-only sieve check: query Fastmail's sieve scripts to detect if routing rules exist
- Check both per-category routing rules AND the screener catch-all rule
- Sieve statuses: `✓ found`, `✗ missing`, `? unknown` (ambiguous/custom rules)
- Copy-paste sieve snippets shown by default for missing rules only
- `--ui-guide` flag available for Fastmail UI-based instructions instead of sieve snippets
- **Research needed:** Investigate Sieve/set write feasibility — if automating rule creation is practical, include it; if too complex, defer to a future phase

### CLI invocation
- Subcommand: `mailroom setup` (not a standalone script)
- Requires introducing a CLI framework (click or typer — Claude's discretion)
- `--apply` flag to make changes; dry-run by default (no flag = dry-run)
- Backwards-compatible: `python -m mailroom` should still work for the service — Claude decides whether no-args means "run" or requires explicit "run" subcommand

### Failure & recovery
- Continue on failure: attempt all resources, report successes and failures at the end
- Skip dependent resources when parent fails (e.g., skip child mailboxes if Triage/ parent creation fails) — mark as `⊘ skipped (parent failed)`
- Pre-flight connectivity check on both dry-run and apply (verify JMAP + CardDAV credentials before attempting anything)
- Exit codes: 0 = all good, 1 = at least one failure
- Idempotent re-run retries failed resources (successes skipped as "exists")

### Claude's Discretion
- Click vs Typer for CLI framework
- Whether `python -m mailroom` (no subcommand) runs the service or requires `mailroom run`
- Human test strategy for setup script
- Loading skeleton / progress indicator implementation
- Exact sieve rule pattern matching heuristics

</decisions>

<specifics>
## Specific Ideas

- Output should look like terraform plan/apply — structured, scannable, clear about what will change
- Sieve rules purpose: route incoming mail from categorized contacts to the correct triage mailbox (e.g., sender in "Feed" contact group → `Triage/Feed`). Mailroom's sweep handles backlog that rules can't touch (rules only apply to new incoming mail)
- The setup script is complementary to the main service: it provisions the infrastructure, sieve rules handle incoming routing, mailroom service handles triage/sweep of backlog

</specifics>

<deferred>
## Deferred Ideas

- Automated sieve rule creation via JMAP Sieve/set — research feasibility first; if too complex, make this a future phase or todo item

</deferred>

---

*Phase: 07-setup-script*
*Context gathered: 2026-02-26*
