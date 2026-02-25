---
created: 2026-02-25T15:33:22.097Z
title: Fix broken Mermaid chart in architecture docs
area: docs
files:
  - docs/architecture.md:7-16
---

## Problem

The Mermaid flowchart in `docs/architecture.md` (lines 7-16) is not rendering properly. Likely causes:

- `\n` in node labels may need to be `<br/>` for cross-renderer compatibility
- The `&` join syntax on line 15 (`D & E & F & G -->|JMAP sweep| H[...]`) may not be supported in all Mermaid renderers (e.g., GitHub)
- Unquoted special characters (`:` and `@`) in node labels can confuse the Mermaid parser

## Solution

- Wrap node labels containing special characters in double quotes (e.g., `D["CardDAV:<br/>Add to Imbox group"]`)
- Replace `\n` with `<br/>` for line breaks
- If the `&` join syntax doesn't work, split into individual edges (one per source node)
- Test rendering on the target platform (GitHub / docs site) after fixing
