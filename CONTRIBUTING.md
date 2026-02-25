# Contributing to Mailroom

Thanks for your interest in contributing! Mailroom is a small, focused project -- contributions that align with the existing architecture are welcome.

## Development Setup

```bash
git clone https://github.com/HelloThisIsFlo/mailroom.git
cd mailroom
uv sync --group dev
pytest
```

This installs all dependencies (including dev tools like ruff and pytest) and runs the test suite to verify everything works.

## Code Style

The project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting (configured in `pyproject.toml`). Run it before submitting:

```bash
ruff check .
ruff format .
```

## Pull Requests

This repo uses [GSD](https://github.com/HelloThisIsFlo/gsd) for planning and execution. If you're working on anything beyond a trivial fix, please:

1. Check `.planning/` for the project roadmap and phase structure
2. Use `/gsd:plan-phase` to plan your changes -- this keeps PRs coherent and well-scoped
3. Follow the existing commit message conventions (e.g., `feat(phase-plan): description`)

For small bug fixes or documentation improvements, a standard PR with a clear description is fine.

## Human Integration Tests

The `human-tests/` directory contains standalone scripts that run against a real Fastmail account. These are first-class citizens alongside unit tests:

- They are **not** pytest tests -- each is a standalone Python script
- Run them in order: `python human-tests/test_1_auth.py`, `test_2_query.py`, etc.
- They validate real JMAP and CardDAV behavior against live Fastmail

If your change affects email processing or contact management, consider whether an existing human test covers it or whether a new one is needed.

## Project Structure

```
src/mailroom/
  core/          # Config, logging
  jmap/          # JMAP client (email operations)
  carddav/       # CardDAV client (contact management)
  workflow/      # Triage pipeline (ScreenerWorkflow)
tests/           # Unit tests (pytest)
human-tests/     # Integration tests against live Fastmail
.planning/       # GSD project planning, roadmap, phase state
```

## Questions?

Open an issue -- happy to help orient you in the codebase.
