# Phase 15: Milestone Closeout & Cleanup - Context

**Gathered:** 2026-03-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Close all gaps from the v1.2 milestone audit: finalize WIP documentation into proper docs, fix latent integration inconsistency, resolve test cross-contamination, remove dead production code, and update requirement checkboxes. This is a cleanup phase — no new features.

</domain>

<decisions>
## Implementation Decisions

### WIP.md finalization (CLOSE-01)
- Create `docs/workflow.md` from `docs/WIP.md` content — comprehensive triage workflow reference
- Rewrite `docs/config.md` for config.yaml (YAML categories, add_to_inbox, parent, contact_type); keep credentials section (still env vars). Old env-var config docs are replaced entirely.
- Update `docs/architecture.md` to cover the full system: triage pipeline, re-triage, contact provenance tracking, and the reset CLI. Update the mermaid diagram to reflect parent/child categories and label scanning.
- Tone: open-source ready — explain concepts, include examples, provide context for decisions. Written as if someone else might read it.
- Remove `docs/WIP.md` after content is integrated (WIP banner no longer needed)

### infrastructure_groups consistency (integration gap)
- `run_reset()` in `resetter.py` must pass `infrastructure_groups=[settings.mailroom.provenance_group]` to `validate_groups()`, matching the `__main__.py` triage startup path

### structlog cross-contamination fix (test isolation)
- Add `monkeypatch.setattr(resetter_mod, "configure_logging", lambda level: None)` in `TestRunResetConfirmation._run_reset_with_mocks()` to prevent structlog globally rebinding `PrintLoggerFactory`

### Dead code removal
- Remove `_get_destination_mailbox_ids()` from `screener.py` — tested utility never called in production (both triage and re-triage inline equivalent logic in `_reconcile_email_labels()`)
- Remove `batch_move_emails()` from `jmap.py` — superseded by inline `Email/set` patches in `_reconcile_email_labels()`
- Remove corresponding tests for both methods

### RTRI-05 checkbox + RTRI-04 wording alignment
- Update REQUIREMENTS.md: RTRI-05 checkbox from `[ ]` to `[x]`, status from Pending to Complete
- Align RTRI-04 wording between REQUIREMENTS.md and code (docs say "Added to/Moved from", code uses "Triaged to/Re-triaged to")

### Claude's Discretion
- Exact structure and section ordering within workflow.md
- How to organize the architecture.md mermaid diagram (single vs multi-diagram)
- Level of detail in config.md examples
- Whether to update docs/index.html to reference new workflow.md

</decisions>

<specifics>
## Specific Ideas

- Config.md should be rewritten from scratch for config.yaml — not a patch on top of the old env-var docs
- Architecture.md should show the complete operational picture including reset/provenance
- All docs should be self-contained enough for someone unfamiliar with the project to understand

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/WIP.md`: 213-line comprehensive workflow reference — source material for workflow.md
- `docs/architecture.md`: existing structure with mermaid diagram — needs updating, not replacing
- `docs/config.md`: existing config reference — will be rewritten for YAML categories

### Established Patterns
- Docs use standard markdown with mermaid diagrams for architecture
- Config docs use tables for variable reference
- All docs are in `docs/` directory (flat structure)

### Integration Points
- `resetter.py:run_reset()` → `carddav.validate_groups()`: missing infrastructure_groups parameter
- `tests/test_resetter.py:TestRunResetConfirmation._run_reset_with_mocks()`: needs configure_logging mock
- `screener.py:_get_destination_mailbox_ids()` and `jmap.py:batch_move_emails()`: dead code to remove
- `.planning/REQUIREMENTS.md`: RTRI-05 checkbox and RTRI-04 wording to update

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 15-milestone-closeout-cleanup*
*Context gathered: 2026-03-05*
