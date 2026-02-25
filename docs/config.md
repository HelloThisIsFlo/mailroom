# Configuration Reference

All configuration is done via environment variables with the `MAILROOM_` prefix, loaded by [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). Variable names are case-insensitive.

For local development, copy `.env.example` to `.env` and fill in your credentials. For Kubernetes, see the [deployment guide](deploy.md).

---

## Credentials (required)

These have no defaults. Mailroom will not start without them.

| Variable | Type | Description |
|----------|------|-------------|
| `MAILROOM_JMAP_TOKEN` | `str` | Fastmail JMAP API token. Get one at Fastmail > Settings > Privacy & Security > API tokens. |
| `MAILROOM_CARDDAV_USERNAME` | `str` | Your full Fastmail email address (e.g., `you@fastmail.com`). Used for CardDAV authentication. |
| `MAILROOM_CARDDAV_PASSWORD` | `str` | A Fastmail app password with CardDAV access. Create one at Fastmail > Settings > Privacy & Security > Integrations > New app password. |

> **Note:** `MAILROOM_CARDDAV_USERNAME` and `MAILROOM_CARDDAV_PASSWORD` default to empty strings internally for forward compatibility, but Mailroom will fail to connect to CardDAV without valid values.

---

## Polling

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MAILROOM_POLL_INTERVAL` | `int` | `300` | Seconds between poll cycles. Default is 5 minutes. |

---

## Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MAILROOM_LOG_LEVEL` | `str` | `info` | Log verbosity. Valid values: `debug`, `info`, `warning`, `error`. |

---

## Triage Labels

These are Fastmail mailbox/label names that users apply to emails in the Screener to trigger triage. Each label maps to a contact group and email destination.

| Variable | Type | Default | Destination |
|----------|------|---------|-------------|
| `MAILROOM_LABEL_TO_IMBOX` | `str` | `@ToImbox` | Adds sender to **Imbox** group, moves emails to **Inbox** |
| `MAILROOM_LABEL_TO_FEED` | `str` | `@ToFeed` | Adds sender to **Feed** group, moves emails to **Feed** |
| `MAILROOM_LABEL_TO_PAPER_TRAIL` | `str` | `@ToPaperTrail` | Adds sender to **Paper Trail** group, moves emails to **Paper Trail** |
| `MAILROOM_LABEL_TO_JAIL` | `str` | `@ToJail` | Adds sender to **Jail** group, moves emails to **Jail** |
| `MAILROOM_LABEL_TO_PERSON` | `str` | `@ToPerson` | Adds sender to **Imbox** group as a person contact, moves emails to **Inbox** |

---

## System Labels

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MAILROOM_LABEL_MAILROOM_ERROR` | `str` | `@MailroomError` | Applied to emails with triage conflicts (same sender with different labels) or already-grouped errors. |
| `MAILROOM_LABEL_MAILROOM_WARNING` | `str` | `@MailroomWarning` | Applied to emails where the sender's display name doesn't match the existing contact name. |
| `MAILROOM_WARNINGS_ENABLED` | `bool` | `true` | Enable or disable warning label application. When `false`, `@MailroomWarning` is not required to exist in Fastmail. |

---

## Screener

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MAILROOM_SCREENER_MAILBOX` | `str` | `Screener` | The Fastmail mailbox where incoming emails land before triage. |

---

## Contact Groups

These are CardDAV contact group names in Fastmail Contacts. They must be created manually in Fastmail before Mailroom starts.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MAILROOM_GROUP_IMBOX` | `str` | `Imbox` | Contact group for important senders (routed to Inbox). |
| `MAILROOM_GROUP_FEED` | `str` | `Feed` | Contact group for newsletters and updates. |
| `MAILROOM_GROUP_PAPER_TRAIL` | `str` | `Paper Trail` | Contact group for receipts and transactional email. |
| `MAILROOM_GROUP_JAIL` | `str` | `Jail` | Contact group for unwanted but not-quite-spam senders. |

---

## Quick Reference

**Total configurable fields:** 18

- 3 credentials (required)
- 1 polling setting
- 1 logging setting
- 5 triage labels
- 3 system labels
- 1 screener mailbox
- 4 contact groups

See `.env.example` in the project root for a ready-to-use template with all variables and placeholder values.
