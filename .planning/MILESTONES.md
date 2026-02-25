# Milestones

## v1.0 MVP (Shipped: 2026-02-25)

**Delivered:** HEY Mail's Screener workflow on Fastmail — one label tap triages an entire sender, sweeps their backlog, and auto-routes future emails.

**Stats:** 6 phases, 18 plans | 8,666 LOC Python | 180 tests + 13 human integration tests | 122 files | 3 days

**Git range:** `feat(01-01)` → `feat(05-01)` | Tag: `v1.0`

**Key accomplishments:**
- JMAP client with session discovery, mailbox resolution, email query/move/relabel, and batch chunking
- CardDAV client with contact search/create/group membership, ETag conflict handling, validated against live Fastmail
- Screener triage pipeline: poll → conflict detect → upsert contact → sweep emails → remove triage label, with retry safety
- Person/company contact types via @ToPerson label with nameparser, @MailroomWarning for name mismatches
- Docker + k8s deployment: multi-stage build, k8s manifests (namespace, configmap, secret, deployment), GitHub Actions CI, health endpoint
- Documentation: README, deployment guide, architecture docs, animated product showcase page

**Bonus deliveries (beyond v1 requirements):**
- TRIAGE-11 (sender display name preservation) — delivered in Phase 3
- OPS-02 (health/liveness probe) — delivered in Phase 4
- Phase 3.1 (person/company contact types) — inserted phase beyond original scope

**Tech debt (Info severity):**
- REQUIREMENTS.md traceability missing Phase 3.1 extensions (doc gap only)
- Duplicate "Inbox" in required_mailboxes (functionally harmless)
- Latent KeyError in _apply_warning_label (guarded by call site, not reachable)
- SUMMARY.md files lack requirements-completed frontmatter

**Archives:** `milestones/v1.0-ROADMAP.md`, `milestones/v1.0-REQUIREMENTS.md`, `milestones/v1.0-MILESTONE-AUDIT.md`

---

