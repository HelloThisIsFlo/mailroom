---
phase: 13
slug: re-triage
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-03
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, 330 tests passing) |
| **Config file** | `tests/conftest.py` (existing, with mock_settings and mock_mailbox_ids) |
| **Quick run command** | `python -m pytest tests/ -x --tb=short -q` |
| **Full suite command** | `python -m pytest tests/ -x --tb=short -q` |
| **Estimated runtime** | ~1 second |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x --tb=short -q`
- **After every plan wave:** Run `python -m pytest tests/ -x --tb=short -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | RTRI-01 | unit | `python -m pytest tests/test_carddav_client.py -k "remove_from_group" -x` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | RTRI-04 | unit | `python -m pytest tests/test_carddav_client.py -k "triage_history" -x` | ❌ W0 | ⬜ pending |
| 13-01-03 | 01 | 1 | RTRI-02 | unit | `python -m pytest tests/test_jmap_client.py -k "query_emails_by_sender" -x` | ❌ W0 | ⬜ pending |
| 13-02-01 | 02 | 2 | RTRI-01 | unit | `python -m pytest tests/test_screener_workflow.py -k "retriage" -x` | ❌ W0 | ⬜ pending |
| 13-02-02 | 02 | 2 | RTRI-02 | unit | `python -m pytest tests/test_screener_workflow.py -k "reconcil" -x` | ❌ W0 | ⬜ pending |
| 13-02-03 | 02 | 2 | RTRI-03 | unit | `python -m pytest tests/test_screener_workflow.py -k "group_reassigned" -x` | ❌ W0 | ⬜ pending |
| 13-02-04 | 02 | 2 | RTRI-06 | unit | `python -m pytest tests/test_screener_workflow.py -k "inbox_retriage" -x` | ❌ W0 | ⬜ pending |
| 13-03-01 | 03 | 3 | RTRI-05 | manual-only | `python human-tests/test_17_retriage.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_carddav_client.py` — new tests for `remove_from_group()` and triage history note format
- [ ] `tests/test_jmap_client.py` — new tests for `query_emails_by_sender()`
- [ ] `tests/test_screener_workflow.py` — new tests for re-triage scenarios (replacing TestAlreadyGroupedDifferentGroup behavior)
- [ ] `human-tests/test_17_retriage.py` — new human integration test
- [ ] `human-tests/test_9_already_grouped.py` — early exit redirect

*Existing tests that will need updates:*
- `TestAlreadyGroupedDifferentGroup` (test_screener_workflow.py) — currently asserts error label; must change to assert re-triage
- `TestAlreadyGroupedSameGroup` (test_screener_workflow.py) — must change to assert same-group re-triage with reconciliation
- `upsert_contact` tests in test_carddav_client.py — NOTE format changes

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full re-triage workflow against live Fastmail | RTRI-05 | Requires real JMAP/CardDAV server | Run `python human-tests/test_17_retriage.py` against live account |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
