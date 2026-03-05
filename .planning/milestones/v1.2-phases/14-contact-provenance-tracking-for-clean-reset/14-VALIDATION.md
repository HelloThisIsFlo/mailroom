---
phase: 14
slug: contact-provenance-tracking-for-clean-reset
status: draft
nyquist_compliant: true
wave_0_complete: true
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
| 14-01-01 | 01 | 1 | Config rename (PROV-01) | unit | `pytest tests/test_config.py -x` | Needs update | ⬜ pending |
| 14-01-02 | 01 | 1 | Old labels rejected (PROV-02) | unit | `pytest tests/test_config.py -x` | Needs new test | ⬜ pending |
| 14-01-03 | 01 | 1 | Provenance group validation | unit | `pytest tests/test_config.py -x` | Needs new test | ⬜ pending |
| 14-01-04 | 01 | 1 | Setup provisioner (PROV-03) | unit | `pytest tests/test_provisioner.py -x` | Needs update | ⬜ pending |
| 14-02-01 | 02 | 2 | Provenance note created (PROV-05) | unit | `pytest tests/test_carddav_client.py -x` | Needs update | ⬜ pending |
| 14-02-02 | 02 | 2 | Provenance note adopted (PROV-05) | unit | `pytest tests/test_carddav_client.py -x` | Needs update | ⬜ pending |
| 14-02-03 | 02 | 2 | Provenance group add (PROV-04) | unit | `pytest tests/test_carddav_client.py -x` | Needs new test | ⬜ pending |
| 14-02-04 | 02 | 2 | Provenance group skip (PROV-04) | unit | `pytest tests/test_carddav_client.py -x` | Needs new test | ⬜ pending |
| 14-02-05 | 02 | 2 | check_membership exclusion (PROV-06) | unit | `pytest tests/test_carddav_client.py -x` | Needs new test | ⬜ pending |
| 14-02-06 | 02 | 2 | @MailroomWarning cleanup (PROV-07) | unit | `pytest tests/test_screener_workflow.py -x` | Needs new test | ⬜ pending |
| 14-02-07 | 02 | 2 | @MailroomWarning reapply (PROV-07) | unit | `pytest tests/test_screener_workflow.py -x` | Needs new test | ⬜ pending |
| 14-03-01 | 03 | 3 | delete_contact + batch_add_labels (PROV-08) | unit | `pytest tests/test_carddav_client.py -x` | Needs new test | ⬜ pending |
| 14-03-02 | 03 | 3 | User-modified detection (PROV-09) | unit | `pytest tests/test_resetter.py -x` | Needs new test | ⬜ pending |
| 14-03-03 | 03 | 3 | Reset provenance DELETE (PROV-10) | unit | `pytest tests/test_resetter.py -x` | Needs update | ⬜ pending |
| 14-03-04 | 03 | 3 | Reset provenance WARN (PROV-10) | unit | `pytest tests/test_resetter.py -x` | Needs new test | ⬜ pending |
| 14-03-05 | 03 | 3 | Reset adopted cleanup (PROV-10) | unit | `pytest tests/test_resetter.py -x` | Needs update | ⬜ pending |
| 14-03-06 | 03 | 3 | Reset operation order (PROV-11) | unit | `pytest tests/test_resetter.py -x` | Needs update | ⬜ pending |

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
