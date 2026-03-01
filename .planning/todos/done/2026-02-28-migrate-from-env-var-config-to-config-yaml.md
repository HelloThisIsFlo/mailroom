---
created: 2026-02-28T02:49:00.000Z
title: Migrate from env var config to config.yaml
area: config
priority: high
files:
  - src/mailroom/core/config.py
  - k8s/configmap.yaml
  - .env.example
---

## Problem

The env var config system has outgrown its usefulness. Structured data like `MAILROOM_TRIAGE_CATEGORIES` requires JSON-in-a-string, which is:
- Unreadable as a single line in `.env`
- Breaks direnv when multiline (direnv parses `.env` line by line)
- No comments possible inside the JSON
- No hierarchy — everything is flat `MAILROOM_` prefixed strings
- Awkward to override locally (copy the whole JSON blob, edit, paste back)

This became obvious when adding Billboard/Truck child categories — the config is already complex enough to warrant a proper config file.

## Solution

Replace env var config with a `config.yaml` loaded by the application:
- App loads `config.yaml` (with a default search path: `./config.yaml`, `/etc/mailroom/config.yaml`)
- Env vars can still override individual fields (pydantic-settings supports layered sources)
- Triage categories become readable YAML instead of JSON-in-string
- Kubernetes: mount as a ConfigMap volume instead of envFrom
- Local dev: just edit `config.yaml` directly

Example of what config.yaml would look like:
```yaml
poll_interval: 60
debounce_seconds: 3
screener_mailbox: Screener

triage_categories:
  - name: Imbox
    destination_mailbox: Inbox
  - name: Feed
  - name: Paper Trail
  - name: Billboard
    parent: Paper Trail
    contact_group: Billboard
    destination_mailbox: Paper Trail/Billboard
```

## Priority

High — should be the first thing in the next milestone, or inserted as a phase in the current one. The current env var config is workable but painful for any customization. This also pairs well with the Helm migration (values.yaml naturally maps to config.yaml).
