# Phase 5: Documentation, Deployment Guide, and Showcase Page - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Add comprehensive documentation and a marketing showcase page. Deliverables: README rewrite, docs/ folder (deploy guide, config reference, architecture overview, future vision), showcase HTML page for GitHub Pages, .env.example, LICENSE (AGPL), and CONTRIBUTING.md. No new features or code changes to the application itself.

</domain>

<decisions>
## Implementation Decisions

### README Structure
- One-liner tagline: Fastmail-specific ("One-label email triage for Fastmail")
- Badges at top: Python version, AGPL license, CI/CD status (love automated badges)
- Problem statement section: 2-3 sentences referencing HEY by Basecamp and Google Inbox as workflow inspiration — Mailroom brings those powerful triage workflows to Fastmail's flexibility
- Features bullet list: JMAP + CardDAV pipeline, 4 destinations, person vs company contacts, retry safety
- Quick Start: Docker first (`docker run`), then "From Source" with pip/venv
- Deploy section: link to docs/deploy.md
- Configuration section: link to docs/config.md
- Testing section: pytest + human integration tests
- Prominent link to showcase page (GitHub Pages) near the top
- GSD footer line at bottom: "Built with GSD" linking to GSD
- Architecture: one-liner + link to docs/architecture.md (optionally a tiny inline diagram near features — Claude's discretion on whether it clutters)

### .env.example
- Commit .env.example with all MAILROOM_ env vars and placeholder values
- Quick Start references it for the "From Source" path

### License
- AGPL-3.0 license file + badge
- Open-core strategy: public engine, future closed SaaS layer (OAuth, UI, billing) in separate repo

### Showcase Page
- **Vibe:** Product/consumer (Notion, Superhuman feel) — bright, friendly, not dev-techy
- **Sections in order:** Hero + tagline → Animated workflow demo → Feature highlights (3-4 cards) → "Coming soon" / "Extendable" teaser at the end
- **Main animation:** Animated demo of the core triage workflow as the centerpiece — must be clear and immediately understandable
- **CTA:** "View on GitHub" button (replace with sign-up when SaaS launches)
- **Branding:** Fastmail-specific ("for Fastmail" — probably forever)
- **Footer:** "Built by Flo"
- **No GSD mention** on the showcase page — it's product marketing, not dev tooling
- **Color scheme:** Claude's discretion — should match product/consumer vibe

### Docs Folder
- `docs/deploy.md` — Step-by-step Kubernetes walkthrough: build image, create namespace, apply secrets, apply manifests, verify. Copy-pasteable commands. Assumes k8s familiarity.
- `docs/config.md` — Hand-written configuration reference for all MAILROOM_ env vars. No auto-generation; the config model is small.
- `docs/architecture.md` — Mermaid diagram showing the triage pipeline + short text explaining each component (JMAP client, CardDAV client, ScreenerWorkflow). Brief mention of .planning/ folder: "managed by GSD."
- `docs/FUTURE.md` — Open-core vision notes: hosted SaaS service, OAuth Fastmail login, UI for advanced rules/rule builder, infrastructure. Strategic notes for the author, not marketing.
- GitHub Pages setup to serve showcase from docs/ (Claude's discretion on exact approach: docs/ on main vs gh-pages branch)

### CONTRIBUTING.md
- Short contributing guidelines
- Key point: use GSD for planning if submitting PRs, to keep the repo coherent
- Reference the .planning/ workflow

### Claude's Discretion
- Animation design approach (storyboard, CSS technique, vanilla JS vs framework)
- Showcase page tech stack (single HTML file vs lightweight generator)
- Color palette for showcase page
- Whether a tiny triage flow diagram fits in the README features section without clutter
- GitHub Pages deployment approach (docs/ on main vs gh-pages branch)
- Exact badge styling and placement

</decisions>

<specifics>
## Specific Ideas

- "I migrated from HEY — their workflow was amazing. Fastmail is very flexible but only filters on arrival. Mailroom lets you implement complex workflows on top of Fastmail. The power of HEY and Google Inbox was really their workflow."
- README should be very short — the codebase is small, documentation should match
- Showcase page should "sell" the project as if it were SaaS — marketing tone, not technical docs
- "And more coming" or "Extendable" teaser at the end of the showcase page for future use cases
- FUTURE.md captures the open-core direction: public engine stays open source, closed SaaS layer (OAuth, hosted, UI) builds on top — like Plausible, Cal.com, Supabase model

</specifics>

<deferred>
## Deferred Ideas

- **Coffee tip jar / support link** — Add to showcase page, README, and even logs (non-obtrusive, best practices). Show it everywhere a user might see it without being pushy. Set up the actual tip jar service first.
- **License strategy evolution** — Re-evaluate AGPL if expanding to other email providers or launching SaaS tier
- **SaaS layer** — OAuth Fastmail login, hosted infrastructure, rule builder UI, billing — separate private repo, builds on the open-source engine

</deferred>

---

*Phase: 05-add-documentation-deployment-guide-and-project-showcase-page*
*Context gathered: 2026-02-25*
