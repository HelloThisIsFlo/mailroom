---
created: 2026-02-25T15:35:04.155Z
title: Fix failing GitHub Actions workflow
area: tooling
files:
  - .github/workflows/build.yaml
---

## Problem

The `docker/build-push-action@v6` step fails with:
```
ERROR: failed to build: Cache export is not supported for the docker driver.
```

The workflow uses `cache-from: type=gha` and `cache-to: type=gha,mode=max`, but the default `docker` buildx driver doesn't support GHA cache backends.

## Solution

Add `docker/setup-buildx-action@v3` step before the build step. This creates a builder using the `docker-container` driver which supports GHA cache export. Fix already applied locally.
