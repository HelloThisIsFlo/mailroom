# Mailroom

This project is managed by GSD commands (`/gsd:help` for usage). All planning context, roadmaps, and phase state live in `.planning/`.

## Human Integration Tests

`human-tests/` contains standalone scripts that run against the real Fastmail account (run in order, `python human-tests/test_N_name.py`). These are first-class citizens — when planning, building, or verifying features, always consider whether a human test covers or should cover the behavior.
