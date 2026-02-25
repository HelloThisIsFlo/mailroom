---
created: 2026-02-25T16:53:50.330Z
title: Consolidate .env.example and load from root in human tests
area: testing
files:
  - .env.example
  - human-tests/.env.example
  - human-tests/
---

## Problem

There are two `.env.example` files: one at the project root and one in `human-tests/`. This is redundant — the root one is the canonical source. The human test scripts currently load their `.env` from the `human-tests/` directory, which means credentials need to be duplicated.

## Solution

- Remove `human-tests/.env.example` (root `.env.example` is the single source of truth)
- Update all human test scripts to load `.env` from the project root instead of `human-tests/`
- Can be done together with the `.research/` folder setup as a quick repo cleanup task
