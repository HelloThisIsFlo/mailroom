---
phase: 14
slug: contact-provenance-tracking-for-clean-reset
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-04
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (latest, already configured) |
| **Config file** | `pyproject.toml` (ruff + pytest config) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | Config rename | unit | `pytest tests/test_config.py -x` | Needs update | ⬜ pending |
| 14-01-02 | 01 | 1 | Old labels rejected | unit | `pytest tests/test_config.py -x` | Needs new test | ⬜ pending |
| 14-01-03 | 01 | 1 | Provenance group validation | unit | `pytest tests/test_config.py -x` | Needs new test | ⬜ pending |
| 14-02-01 | 02 | 1 | Provenance note (created) | unit | `pytest tests/test_carddav_client.py -x` | Needs update | ⬜ pending |
| 14-02-02 | 02 | 1 | Provenance note (adopted) | unit | `pytest tests/test_carddav_client.py -x` | Needs update | ⬜ pending |
| 14-02-03 | 02 | 1 | Provenance group add | unit | `pytest tests/test_carddav_client.py -x` | Needs new test | ⬜ pending |
| 14-02-04 | 02 | 1 | Provenance group skip | unit | `pytest tests/test_carddav_client.py -x` | Needs new test | ⬜ pending |
| 14-02-05 | 02 | 1 | check_membership exclusion | unit | `pytest tests/test_carddav_client.py -x` | Needs new test | ⬜ pending |
| 14-02-06 | 02 | 1 | delete_contact | unit | `pytest tests/test_carddav_client.py -x` | Needs new test | ⬜ pending |
| 14-03-01 | 03 | 2 | @MailroomWarning cleanup | unit | `pytest tests/test_screener_workflow.py -x` | Needs new test | ⬜ pending |
| 14-03-02 | 03 | 2 | @MailroomWarning reapply | unit | `pytest tests/test_screener_workflow.py -x` | Needs new test | ⬜ pending |
| 14-04-01 | 04 | 2 | User-modified detection | unit | `pytest tests/test_resetter.py -x` | Needs new test | ⬜ pending |
| 14-04-02 | 04 | 2 | Reset provenance DELETE | unit | `pytest tests/test_resetter.py -x` | Needs update | ⬜ pending |
| 14-04-03 | 04 | 2 | Reset provenance WARN | unit | `pytest tests/test_resetter.py -x` | Needs new test | ⬜ pending |
| 14-04-04 | 04 | 2 | Reset adopted cleanup | unit | `pytest tests/test_resetter.py -x` | Needs update | ⬜ pending |
| 14-04-05 | 04 | 2 | Reset operation order | unit | `pytest tests/test_resetter.py -x` | Needs update | ⬜ pending |
| 14-05-01 | 05 | 1 | Setup provisioner | unit | `pytest tests/test_provisioner.py -x` | Needs update | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Update `tests/conftest.py` — `mock_settings` fixture must produce settings with `mailroom` section instead of `labels`
- [ ] Update `config.yaml.example` — rename `labels:` to `mailroom:` with new key names
- [ ] No new framework installs needed — pytest infrastructure is complete

*Existing infrastructure covers framework needs. Wave 0 is config fixture updates only.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Provenance group created in real Fastmail | Setup provisioner | Real CardDAV server needed | Run `human-tests/test_N_setup.py`, verify group exists |
| Reset deletes real contacts | Reset pipeline | Destructive real operation | Run reset human test with test contacts |
| @MailroomWarning visible in Fastmail UI | Warning cleanup | UI verification | Triage a sender, check label in Fastmail |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
