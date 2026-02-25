---
created: 2026-02-25T16:53:50.330Z
title: Create .research folder for non-planning research and discovery
area: tooling
files: []
---

## Problem

Currently there's no dedicated space for research artifacts that aren't part of formal planning phases. Things like:
- Discovery scripts (e.g., JMAP EventSource logging)
- Personal notes and findings
- The original project brief (which predates `.planning/` and is now fully captured there)
- Future research on new topics

These don't belong in `.planning/` (which is phase/milestone-oriented) and shouldn't pollute the main source tree, but they should still be committed and versioned.

## Solution

- Create a `.research/` top-level directory
- Organize by theme, not by type — e.g., `.research/jmap-eventsource/` would contain both the discovery script and any notes about push architecture
- Move the original project brief into `.research/` as historical context
- Keep it committed (not gitignored) so it travels with the repo
- Discovery scripts from other todos (e.g., JMAP EventSource discovery script) would live here instead of `human-tests/`
- Lightweight structure — no strict conventions, just a free space for exploration
