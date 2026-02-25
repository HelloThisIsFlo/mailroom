# Phase 5: Documentation, Deployment Guide, and Showcase Page - Research

**Researched:** 2026-02-25
**Domain:** Documentation, static site (GitHub Pages), open-source project packaging
**Confidence:** HIGH

## Summary

Phase 5 is a pure documentation and presentation phase with no application code changes. The deliverables are: a rewritten README with badges, a `docs/` folder containing four markdown documents (deploy.md, config.md, architecture.md, FUTURE.md), a single-file HTML showcase page served via GitHub Pages from `docs/`, a root `.env.example`, an AGPL-3.0 LICENSE file, and a CONTRIBUTING.md.

The technical risk is low. All deliverables are static content. The showcase page is the only component with meaningful implementation complexity -- it requires a CSS-animated workflow demo that communicates the core value proposition ("one label tap triages an entire sender") in a consumer-friendly, product-marketing style. The animation should use pure CSS keyframes with minimal vanilla JS for scroll-triggered activation. No build tools, no frameworks, no dependencies.

GitHub Pages deployment from `docs/` on the `main` branch is the simplest approach: enable it once in repo settings, and every push to main auto-publishes. The `docs/index.html` file becomes the showcase page; the markdown files (deploy.md, config.md, etc.) are consumed on GitHub's code browser, not served by Pages.

**Primary recommendation:** Single-file `docs/index.html` with inline CSS/JS for the showcase page. Pure CSS keyframes for the workflow animation. All documentation in markdown consumed via GitHub. No build step, no generator, no external dependencies.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **README Structure:** One-liner tagline ("One-label email triage for Fastmail"), badges (Python, AGPL, CI/CD), problem statement referencing HEY/Google Inbox, features list, Quick Start (Docker first, then source), links to docs/, prominent showcase link, GSD footer
- **.env.example:** Commit with all MAILROOM_ env vars and placeholder values
- **License:** AGPL-3.0 file + badge, open-core strategy noted
- **Showcase Vibe:** Product/consumer (Notion, Superhuman feel) -- bright, friendly, not dev-techy
- **Showcase Sections:** Hero + tagline -> Animated workflow demo -> Feature highlights (3-4 cards) -> "Coming soon" teaser
- **Showcase Animation:** Animated demo of core triage workflow as centerpiece -- must be clear and immediately understandable
- **Showcase CTA:** "View on GitHub" button
- **Showcase Branding:** Fastmail-specific, "Built by Flo" footer, no GSD mention
- **Docs Folder:** deploy.md (k8s walkthrough), config.md (hand-written env var reference), architecture.md (Mermaid diagram + component text), FUTURE.md (open-core vision notes)
- **CONTRIBUTING.md:** Short, references GSD planning workflow

### Claude's Discretion
- Animation design approach (storyboard, CSS technique, vanilla JS vs framework)
- Showcase page tech stack (single HTML file vs lightweight generator)
- Color palette for showcase page
- Whether a tiny triage flow diagram fits in the README features section without clutter
- GitHub Pages deployment approach (docs/ on main vs gh-pages branch)
- Exact badge styling and placement

### Deferred Ideas (OUT OF SCOPE)
- Coffee tip jar / support link -- set up tip jar service first
- License strategy evolution -- re-evaluate AGPL if expanding
- SaaS layer -- OAuth, hosted infra, rule builder UI, billing (separate private repo)
</user_constraints>

## Standard Stack

### Core
| Component | Version/Format | Purpose | Why Standard |
|-----------|---------------|---------|--------------|
| HTML5 + CSS3 | Current | Showcase page | Zero dependencies, GitHub Pages serves static files natively |
| CSS Keyframes | CSS3 | Workflow animation | No JS library needed, smooth 60fps, works everywhere |
| Mermaid | GitHub-native | Architecture diagram in docs/architecture.md | GitHub renders mermaid code blocks natively since 2022 |
| Shields.io | Hosted service | README badges | De facto standard for open-source project badges |
| GitHub Pages | docs/ on main | Showcase hosting | Zero config after initial setup, free, tied to repo |

### Supporting
| Component | Purpose | When to Use |
|-----------|---------|-------------|
| Vanilla JS (~20 lines) | IntersectionObserver for scroll-triggered animation | Only if animation should play on scroll-into-view |
| CSS custom properties | Color palette, spacing tokens | Keep showcase page themeable with minimal code |
| `@media (prefers-reduced-motion)` | Accessibility | Respect user's motion preferences |
| `<meta name="viewport">` | Mobile responsive | Showcase must look good on mobile |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Single HTML file | Static site generator (Hugo, Astro) | Generator adds build step, dependency, complexity -- overkill for one page |
| CSS keyframes | Lottie / Rive | Vector animation libraries add JS dependencies and JSON assets -- unnecessary for a step-by-step workflow demo |
| Vanilla JS | GSAP / anime.js | Animation libraries are powerful but add weight for what amounts to sequenced CSS class toggling |
| docs/ on main | gh-pages branch | Separate branch adds maintenance burden, harder to keep in sync -- docs/ on main is simpler |

**Installation:** None required. All deliverables are static files.

## Architecture Patterns

### Recommended Deliverable Structure
```
.
├── .env.example              # All MAILROOM_ env vars with placeholders
├── CONTRIBUTING.md            # Short contribution guide
├── LICENSE                    # AGPL-3.0 full text
├── README.md                  # Rewritten project README
└── docs/
    ├── index.html             # Showcase page (GitHub Pages entry point)
    ├── deploy.md              # Kubernetes deployment walkthrough
    ├── config.md              # Environment variable reference
    ├── architecture.md        # Mermaid diagram + component descriptions
    └── FUTURE.md              # Open-core vision notes
```

### Pattern 1: Single-File Showcase Page
**What:** Everything (HTML, CSS, JS) in one `docs/index.html` file with inline styles and script.
**When to use:** When the page is self-contained, has no build step, and needs to be trivially deployable.
**Why:** No asset pipeline, no broken relative paths, no CORS issues, copy-paste deployable. GitHub Pages serves it as-is.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mailroom - One-label email triage for Fastmail</title>
  <style>
    /* All styles inline -- no external CSS file */
    :root {
      --primary: #...;
      --accent: #...;
    }
    /* ... */
  </style>
</head>
<body>
  <!-- Hero, animation, features, CTA -->
  <script>
    // Optional: IntersectionObserver for scroll-triggered animation
  </script>
</body>
</html>
```

### Pattern 2: CSS Keyframe Workflow Animation
**What:** A step-by-step animated sequence showing the triage flow using pure CSS animations with `@keyframes` and `animation-delay` for choreography.
**When to use:** For the showcase page centerpiece -- the workflow demo.
**Design approach:**

The animation should visually tell the story:
1. An email arrives in the Screener (envelope icon slides in)
2. User applies a triage label (label badge appears on the email)
3. Mailroom processes: contact created, emails swept to destination
4. Result: future emails auto-route (show the "after" state)

```css
@keyframes slide-in {
  from { transform: translateX(-100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

@keyframes label-appear {
  from { transform: scale(0); }
  to { transform: scale(1); }
}

.step-1 { animation: slide-in 0.6s ease-out 0s forwards; }
.step-2 { animation: label-appear 0.4s ease-out 0.8s forwards; }
.step-3 { animation: slide-in 0.6s ease-out 1.4s forwards; }
/* Each step uses animation-delay for sequencing */
```

**Key technique:** Use `animation-fill-mode: forwards` so each step holds its end state. Sequence steps via `animation-delay`. The entire animation can loop with a pause using a longer total duration.

### Pattern 3: GitHub-Native Mermaid for Architecture Docs
**What:** Use fenced mermaid code blocks in `docs/architecture.md` for the pipeline diagram.
**When to use:** For architecture documentation rendered on GitHub.

```markdown
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

GitHub renders this natively -- no plugins, no image generation needed.

### Pattern 4: Shields.io Badge URLs
**What:** Dynamic badges at top of README.
**Badges specified by user:** Python version, AGPL license, CI/CD status.

```markdown
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green)
![Build](https://img.shields.io/github/actions/workflow/status/HelloThisIsFlo/mailroom/build.yaml?branch=main&label=build)
```

The GitHub Actions badge references the workflow file `build.yaml` (confirmed in `.github/workflows/build.yaml`). The repo slug is `HelloThisIsFlo/mailroom` (confirmed from git remote).

### Anti-Patterns to Avoid
- **Over-engineering the showcase:** No React, no Tailwind, no bundler. A single HTML file with inline CSS is the right scope for a one-page marketing site.
- **Auto-generating config docs:** The user explicitly decided hand-written config.md. The config model is small (20 env vars). Auto-generation adds complexity for negligible benefit.
- **Putting documentation prose in the showcase page:** The showcase is marketing ("sell the project"). Technical docs stay in markdown files.
- **Committing the AGPL license as LICENSE.md:** Use `LICENSE` (no extension) -- this is what GitHub's license detection expects.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Badges | Custom SVG badge images | Shields.io hosted URLs | Always up-to-date, consistent styling, zero maintenance |
| Architecture diagram | Manual ASCII art or image file | Mermaid code block in markdown | GitHub renders natively, easy to update, version-controlled |
| License text | Write your own license | Copy AGPL-3.0 from gnu.org or github.com/jslicense/AGPL-3.0 | Must be verbatim to be legally valid |
| Static site hosting | Custom deploy scripts | GitHub Pages from docs/ on main | Built-in, zero-config after enabling |

**Key insight:** This phase has no custom infrastructure to build. Every component either uses a hosted service (Shields.io, GitHub Pages) or is hand-authored content (markdown, HTML/CSS). The only "engineering" is the CSS animation.

## Common Pitfalls

### Pitfall 1: GitHub Pages Not Serving index.html
**What goes wrong:** Enabling GitHub Pages but the site shows a 404 or renders README.md instead of the showcase page.
**Why it happens:** Wrong source configuration (root instead of /docs), or missing index.html in the docs/ folder.
**How to avoid:** After creating `docs/index.html`, go to repo Settings > Pages > Source: "Deploy from a branch" > Branch: `main` > Folder: `/docs`. Verify the URL responds with the showcase page.
**Warning signs:** Site shows raw markdown or the repo README instead of the showcase.

### Pitfall 2: Animation Not Playing on Mobile
**What goes wrong:** CSS animations that depend on hover or viewport width break on mobile devices.
**Why it happens:** Using `:hover` for triggering, fixed-width layouts, or animations that assume desktop viewport.
**How to avoid:** Use IntersectionObserver (scroll-into-view) for triggering, not hover. Use responsive units (%, vw, rem). Test at 375px width minimum.
**Warning signs:** Animation works on desktop but is static or broken on phone.

### Pitfall 3: Showcase Page Color/Font Loading Issues
**What goes wrong:** Custom fonts or external resources cause FOUC (flash of unstyled content) or slow loading.
**Why it happens:** Linking external font files or CDN resources that block rendering.
**How to avoid:** Use system font stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ...`) for body text. If a display font is needed, use `font-display: swap` and preload it. Prefer no external dependencies.
**Warning signs:** Text flickers on load, page appears unstyled briefly.

### Pitfall 4: Mermaid Diagram Too Complex for GitHub Rendering
**What goes wrong:** Complex Mermaid diagrams with many nodes render poorly or hit GitHub's rendering limits.
**Why it happens:** GitHub's Mermaid support has some limitations on diagram complexity and certain syntax features.
**How to avoid:** Keep the architecture diagram focused -- one high-level pipeline flow, not every method call. Use subgraphs sparingly. Test by previewing on GitHub before merging.
**Warning signs:** Diagram renders as raw text instead of visual, or cuts off.

### Pitfall 5: .env.example Missing Vars or Wrong Defaults
**What goes wrong:** .env.example drifts from the actual config model, confusing users.
**Why it happens:** New env vars added to code but not to .env.example.
**How to avoid:** Derive .env.example directly from `MailroomSettings` class fields. Cross-reference every field in `config.py` with the .env.example output. There are currently 17 configurable fields.
**Warning signs:** User follows Quick Start, gets a `ValidationError` because a required var is missing from .env.example.

### Pitfall 6: AGPL License Detection by GitHub
**What goes wrong:** GitHub doesn't detect the license, badge shows "unknown".
**Why it happens:** License file has wrong name, wrong format, or non-standard modifications.
**How to avoid:** Name the file `LICENSE` (no extension). Use the exact AGPL-3.0 text from gnu.org. Do not modify the text. GitHub's licensee gem will auto-detect it.
**Warning signs:** Repo page doesn't show the license badge in the sidebar.

## Code Examples

### .env.example (All MAILROOM_ Environment Variables)

Derived from `src/mailroom/core/config.py` MailroomSettings class:

```bash
# Mailroom Configuration
# Copy to .env and fill in your credentials:
#   cp .env.example .env

# === Required Credentials (no defaults -- service won't start without these) ===

# Fastmail JMAP API token
# Get at: Fastmail -> Settings -> Privacy & Security -> API tokens
MAILROOM_JMAP_TOKEN=fmu1-your-jmap-token-here

# CardDAV credentials for contact management
# Username: your full Fastmail email address
# Password: a Fastmail app password with CardDAV access
#   Create at: Fastmail -> Settings -> Privacy & Security -> Integrations -> New app password
MAILROOM_CARDDAV_USERNAME=you@fastmail.com
MAILROOM_CARDDAV_PASSWORD=your-app-password-here

# === Polling ===
# MAILROOM_POLL_INTERVAL=300        # Seconds between polls (default: 300 = 5 min)

# === Logging ===
# MAILROOM_LOG_LEVEL=info            # debug, info, warning, error

# === Triage Labels (Fastmail mailbox/label names) ===
# MAILROOM_LABEL_TO_IMBOX=@ToImbox
# MAILROOM_LABEL_TO_FEED=@ToFeed
# MAILROOM_LABEL_TO_PAPER_TRAIL=@ToPaperTrail
# MAILROOM_LABEL_TO_JAIL=@ToJail
# MAILROOM_LABEL_TO_PERSON=@ToPerson

# === System Labels ===
# MAILROOM_LABEL_MAILROOM_ERROR=@MailroomError
# MAILROOM_LABEL_MAILROOM_WARNING=@MailroomWarning
# MAILROOM_WARNINGS_ENABLED=true

# === Screener ===
# MAILROOM_SCREENER_MAILBOX=Screener

# === Contact Groups ===
# MAILROOM_GROUP_IMBOX=Imbox
# MAILROOM_GROUP_FEED=Feed
# MAILROOM_GROUP_PAPER_TRAIL=Paper Trail
# MAILROOM_GROUP_JAIL=Jail
```

### Showcase Page Color Palette Recommendation

The user wants a "Notion, Superhuman feel" -- product/consumer, bright, friendly. Recommendation:

```css
:root {
  /* Light, clean base */
  --bg: #FAFAFA;
  --surface: #FFFFFF;
  --text-primary: #1A1A2E;
  --text-secondary: #6B7280;

  /* Accent -- warm coral/orange to evoke email/communication energy */
  --accent: #FF6B35;
  --accent-light: #FFF0EB;

  /* Secondary -- calm blue for trust/reliability */
  --secondary: #4F7DF2;
  --secondary-light: #EEF2FF;

  /* Functional */
  --success: #10B981;
  --border: #E5E7EB;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
}
```

### README Badge Block

```markdown
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green)
![Build](https://img.shields.io/github/actions/workflow/status/HelloThisIsFlo/mailroom/build.yaml?branch=main&label=build)
```

### GitHub Pages Setup (One-Time Manual Step)

After `docs/index.html` is pushed to main:
1. Go to `github.com/HelloThisIsFlo/mailroom/settings/pages`
2. Under "Build and deployment" > Source: "Deploy from a branch"
3. Branch: `main`, Folder: `/docs`
4. Save

The site will be available at `https://hellothisisflo.github.io/mailroom/`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| README-only docs | README + docs/ folder with focused pages | 2020+ | Keeps README short, deep docs accessible |
| Manual architecture diagrams (images) | Mermaid code blocks in markdown | GitHub Feb 2022 | Diagrams are version-controlled text, always up to date |
| Custom CI for GitHub Pages | "Deploy from branch" with /docs folder | Stable since 2020 | Zero CI config needed |
| External font loading | System font stacks | 2023+ trend | Better performance, no FOUC, no external dependency |

**Deprecated/outdated:**
- GitHub Pages from `master` branch root (still works but `main` + `/docs` is the modern default)
- Jekyll-based GitHub Pages (still the default renderer, but for a single HTML file it is irrelevant -- HTML files are served as-is)

## Open Questions

1. **Showcase page animation storyboard**
   - What we know: The animation should show the triage workflow (email arrives -> user labels -> Mailroom processes -> result). CSS keyframes with animation-delay for sequencing.
   - What's unclear: Exact visual metaphor -- email envelopes? Simplified inbox UI? Abstract flow arrows? This is a design decision, not a technical one.
   - Recommendation: Use a simplified inbox UI metaphor (email rows with sender names, label badges appearing, emails sliding to destination columns). This matches what users actually see in Fastmail and is immediately understandable.

2. **Tiny inline README diagram**
   - What we know: User is open to a small triage flow diagram in the README features section if it doesn't clutter.
   - What's unclear: Whether a Mermaid diagram looks clean enough inline in the README (vs. linking to architecture.md).
   - Recommendation: Skip the inline diagram in README. Mermaid diagrams in README can look heavy and GitHub's rendering adds whitespace. The features bullet list is more scannable. Link to architecture.md for the visual.

3. **GitHub Pages URL path considerations**
   - What we know: Pages will be served from `https://hellothisisflo.github.io/mailroom/`.
   - What's unclear: Whether a custom domain is planned (unlikely for now).
   - Recommendation: Use relative paths in index.html. No assumptions about custom domain.

## Sources

### Primary (HIGH confidence)
- [GitHub Pages docs/folder configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) - Publishing source setup, folder options, entry file requirements
- [GitHub Mermaid support](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams) - Native Mermaid rendering in markdown
- [Shields.io documentation](https://shields.io/) - Badge URL format for GitHub Actions, license, Python version
- Project codebase: `src/mailroom/core/config.py` (all 17 env vars), `k8s/*.yaml` (deployment manifests), `.github/workflows/build.yaml` (CI workflow name), `Dockerfile`, `pyproject.toml`
- [AGPL-3.0 license text](https://github.com/jslicense/AGPL-3.0) - Verbatim license for LICENSE file

### Secondary (MEDIUM confidence)
- [CSS Animation best practices 2026](https://www.light-tech.io/single-post/web-animation-effects-best-practices-for-2026) - Keep animations functional, respect prefers-reduced-motion, performance first
- [Product landing page patterns](https://swipepages.com/blog/landing-page-examples/) - Hero + demo + features + CTA structure is standard
- [Prismic CSS animation examples](https://prismic.io/blog/css-animation-examples) - Keyframe choreography patterns

### Tertiary (LOW confidence)
- None -- all findings verified against primary sources or official documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Static HTML/CSS/Markdown is well-understood, GitHub Pages docs/ deployment is documented by GitHub
- Architecture: HIGH - All deliverables are clearly scoped static files, no moving parts
- Pitfalls: HIGH - Known issues with GitHub Pages, mobile CSS, and license detection are well-documented
- Animation design: MEDIUM - CSS keyframe choreography is well-understood technically, but the specific visual design for the workflow demo is a creative decision that will need iteration

**Research date:** 2026-02-25
**Valid until:** 2026-06-25 (stable domain -- static content, no fast-moving dependencies)
