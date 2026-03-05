# Configuration Reference

Mailroom uses a combination of a YAML configuration file (`config.yaml`) for service settings and environment variables for authentication credentials. This document covers both.

---

## Credentials (Environment Variables)

Authentication credentials are always set via environment variables -- they never go in the config file. Mailroom will not start without valid credentials.

| Variable | Type | Description |
|----------|------|-------------|
| `MAILROOM_JMAP_TOKEN` | `str` | Fastmail JMAP API token. Get one at Fastmail > Settings > Privacy & Security > API tokens. |
| `MAILROOM_CARDDAV_USERNAME` | `str` | Your full Fastmail email address (e.g., `you@fastmail.com`). Used for CardDAV authentication. |
| `MAILROOM_CARDDAV_PASSWORD` | `str` | A Fastmail app password with CardDAV access. Create one at Fastmail > Settings > Privacy & Security > Integrations > New app password. |

For local development, copy `.env.example` to `.env` and fill in your credentials. For Kubernetes, see the [deployment guide](deploy.md).

---

## Config File Location

Mailroom reads its configuration from `config.yaml` in the current working directory by default. To use a different path, set the `MAILROOM_CONFIG` environment variable:

```bash
export MAILROOM_CONFIG=/path/to/config.yaml
```

To get started, copy the example config:

```bash
cp config.yaml.example config.yaml
```

If the config file is missing, Mailroom exits with a helpful error message pointing to `config.yaml.example`.

---

## Triage Categories

The `triage:` section defines the Screener mailbox and the list of triage categories.

```yaml
triage:
  screener_mailbox: Screener
  categories:
    - name: Imbox
      add_to_inbox: true
    - Feed
    - Paper Trail
    - Jail
    - name: Person
      parent: Imbox
      contact_type: person
    - name: Billboard
      parent: Paper Trail
    - name: Truck
      parent: Paper Trail
```

### screener_mailbox

The Fastmail mailbox where incoming emails land before triage. Default: `Screener`.

### categories

A list of triage categories. Each category can be specified as a full object or as a string shorthand.

**String shorthand:** `- Feed` is equivalent to `- name: Feed` with all defaults.

**Category fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | (required) | Category name. Used to derive label, contact group, and destination mailbox. |
| `parent` | `str` | `null` | Name of another category to establish a parent-child hierarchy. Parent relationship is additive only -- see [workflow.md](workflow.md). |
| `contact_type` | `"company"` or `"person"` | `"company"` | Determines vCard format. Use `"person"` for individual people (parses first/last name). |
| `add_to_inbox` | `bool` | `false` | When `true`, emails from Screener also appear in Inbox at triage time. Per-category, never inherited. |
| `destination_mailbox` | `str` | derived from name | Override the destination mailbox (normally derived from the category name). Cannot be set to `Inbox` -- use `add_to_inbox` instead. |
| `label` | `str` | derived as `@To{Name}` | Override the triage label (normally derived as `@To` + name with spaces removed). |
| `contact_group` | `str` | derived from name | Override the contact group name (normally same as category name). |

**Derived fields:** When left unset, `label` is derived as `@To{Name}` (e.g., `Paper Trail` becomes `@ToPaperTrail`), `contact_group` is the category name, and `destination_mailbox` is the category name.

### Validation

The following rules are checked at startup:

- At least one category is required
- No duplicate names
- All parent references must point to existing categories
- No circular parent chains
- No duplicate labels after derivation
- `destination_mailbox: Inbox` is rejected (use `add_to_inbox` instead)
- No shared contact groups unless categories are related via parent chain

All errors are collected and reported together.

---

## Mailroom Settings

The `mailroom:` section controls operational labels and provenance tracking.

```yaml
mailroom:
  label_error: "@MailroomError"
  label_warning: "@MailroomWarning"
  warnings_enabled: true
  provenance_group: "Mailroom"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `label_error` | `str` | `@MailroomError` | Label applied to emails with triage conflicts (e.g., same sender with different triage labels). |
| `label_warning` | `str` | `@MailroomWarning` | Label applied to emails where the sender's display name does not match the existing contact. |
| `warnings_enabled` | `bool` | `true` | When `false`, warning labels are not applied and `@MailroomWarning` does not need to exist in Fastmail. |
| `provenance_group` | `str` | `Mailroom` | Contact group used to track which contacts Mailroom created (vs adopted pre-existing contacts). Used by the reset command. |

---

## Polling

The `polling:` section controls the fallback poll interval and SSE debounce window.

```yaml
polling:
  interval: 60
  debounce_seconds: 3
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `interval` | `int` | `60` | Seconds between fallback poll cycles. SSE push is the primary trigger; polling is the safety net. |
| `debounce_seconds` | `int` | `3` | SSE event debounce window in seconds. Multiple rapid events are collapsed into a single poll. |

---

## Logging

The `logging:` section controls log verbosity.

```yaml
logging:
  level: info
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `level` | `str` | `info` | Log level. Valid values: `debug`, `info`, `warning`, `error`. |

---

## Full Example

This is the complete `config.yaml.example` shipped with the project:

```yaml
# Mailroom Configuration
# Copy to config.yaml and adjust as needed:
#   cp config.yaml.example config.yaml
#
# Auth credentials (JMAP token, CardDAV username/password) are set via
# environment variables -- see .env.example for required auth env vars.
#
# Override config path: export MAILROOM_CONFIG=/path/to/config.yaml

# --- Polling & Push ---
# SSE push is the primary trigger; polling is the safety net.
polling:
  interval: 60            # Seconds between fallback polls (default: 60)
  debounce_seconds: 3     # SSE event debounce window in seconds (default: 3)

# --- Triage Categories ---
# Each category derives:
#   - label: @To{Name} (e.g., "Imbox" -> "@ToImbox")
#   - contact_group: category name (e.g., "Feed")
#   - destination_mailbox: category name (e.g., "Feed")
#
# Children inherit NOTHING from parent -- they get their own label, group, mailbox.
# Parent relationship = additive only: triage adds child + parent chain labels.
#
# Use string shorthand for simple categories: "- Feed" equals "- name: Feed"
# Use add_to_inbox: true to make emails appear in Inbox (default: false).
# destination_mailbox: Inbox is NOT allowed -- use add_to_inbox instead.
triage:
  screener_mailbox: Screener
  categories:
    - name: Imbox
      add_to_inbox: true
    - Feed
    - Paper Trail
    - Jail
    - name: Person
      parent: Imbox
      contact_type: person
    - name: Billboard
      parent: Paper Trail
    - name: Truck
      parent: Paper Trail

# --- Mailroom Operational Settings ---
mailroom:
  label_error: "@MailroomError"
  label_warning: "@MailroomWarning"
  warnings_enabled: true          # Set false to disable @MailroomWarning label
  provenance_group: "Mailroom"    # Contact group for tracking mailroom-managed contacts

# --- Logging ---
logging:
  level: info               # debug, info, warning, error
```

---

## Quick Reference

**Config sources:**

| Source | What It Provides |
|--------|-----------------|
| Environment variables | Authentication credentials (`MAILROOM_JMAP_TOKEN`, `MAILROOM_CARDDAV_USERNAME`, `MAILROOM_CARDDAV_PASSWORD`) |
| `config.yaml` | Everything else: triage categories, mailroom settings, polling, logging |
| `MAILROOM_CONFIG` env var | Override config file path (default: `config.yaml` in cwd) |

**Top-level YAML sections:** `triage`, `mailroom`, `polling`, `logging`

See [workflow.md](workflow.md) for how categories, parent chains, and `add_to_inbox` work in practice.
