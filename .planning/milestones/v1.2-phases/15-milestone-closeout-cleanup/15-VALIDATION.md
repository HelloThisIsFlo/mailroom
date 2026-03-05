---
phase: 15
slug: milestone-closeout-cleanup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-05
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | CLOSE-01 (infra_groups) | unit | `python -m pytest tests/test_resetter.py -x -q` | ✅ | ⬜ pending |
| 15-01-02 | 01 | 1 | CLOSE-01 (structlog) | integration | `python -m pytest tests/ -x -q` | ✅ | ⬜ pending |
| 15-01-03 | 01 | 1 | CLOSE-01 (dead code) | unit | `python -m pytest tests/ -x -q` | ✅ | ⬜ pending |
| 15-01-04 | 01 | 1 | CLOSE-01 (RTRI-05/04) | manual | visual inspection | ✅ | ⬜ pending |
| 15-02-01 | 02 | 2 | CLOSE-01 (docs) | manual-only | N/A (documentation) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new tests needed; the phase REMOVES tests (dead code) and fixes test isolation (structlog mock).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WIP.md finalized into docs | CLOSE-01 | Documentation content quality | Review workflow.md, config.md, architecture.md for completeness and accuracy |
| RTRI-05/RTRI-04 updates | CLOSE-01 | Text wording in REQUIREMENTS.md | Visual diff of checkbox and wording changes |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
