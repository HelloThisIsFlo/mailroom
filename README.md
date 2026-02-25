![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green)
![Build](https://img.shields.io/github/actions/workflow/status/HelloThisIsFlo/mailroom/build.yaml?branch=main&label=build)

# Mailroom

*One-label email triage for Fastmail*

[See it in action](https://hellothisisflo.github.io/mailroom/)

## The Problem

I migrated from HEY -- their workflow was amazing. Fastmail is incredibly flexible, but it only filters emails on arrival. The power of HEY and Google Inbox was really their workflow: review new senders once, then every future email is automatically routed to the right place. Mailroom brings that triage workflow to Fastmail.

## Features

- **JMAP + CardDAV automated pipeline** -- polls for triaged emails, manages contacts, sweeps messages to their destination
- **4 triage destinations** -- Imbox, Feed, Paper Trail, Jail (apply a label, Mailroom does the rest)
- **Person vs company contact types** -- `@ToPerson` creates contacts with first/last name; all others default to company (ORG field)
- **Retry safety** -- if anything fails mid-processing, the triage label stays and the next poll cycle retries automatically
- **Fully configurable** -- labels, contact groups, polling interval, and logging are all driven by environment variables

## Quick Start

### Docker

```bash
docker run \
  -e MAILROOM_JMAP_TOKEN=fmu1-your-jmap-token \
  -e MAILROOM_CARDDAV_USERNAME=you@fastmail.com \
  -e MAILROOM_CARDDAV_PASSWORD=your-app-password \
  ghcr.io/hellothisisflo/mailroom:latest
```

### From Source

```bash
git clone https://github.com/HelloThisIsFlo/mailroom.git
cd mailroom
cp .env.example .env    # Fill in your Fastmail credentials
uv sync
python -m mailroom
```

## Deploy

Mailroom is designed to run as a long-lived polling service. See [docs/deploy.md](docs/deploy.md) for a step-by-step Kubernetes deployment walkthrough.

## Configuration

All settings are controlled via `MAILROOM_`-prefixed environment variables. See [docs/config.md](docs/config.md) for the full reference.

## Architecture

Mailroom wires a JMAP client (email operations) and a CardDAV client (contact management) into a single triage pipeline. See [docs/architecture.md](docs/architecture.md) for the component diagram and detailed walkthrough.

## Testing

```bash
# Unit tests
pytest

# Human integration tests (run against live Fastmail, in order)
python human-tests/test_1_auth.py
python human-tests/test_2_query.py
# ... see human-tests/ for the full suite
```

## License

[AGPL-3.0](LICENSE)

---

<sub>Built with [GSD](https://github.com/HelloThisIsFlo/gsd)</sub>
