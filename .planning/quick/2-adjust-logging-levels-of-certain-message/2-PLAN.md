---
phase: quick-02
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mailroom/__main__.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "push-triggered poll_completed logs at INFO level"
    - "scheduled and fallback poll_completed logs at DEBUG level"
    - "No other logging behavior changes"
  artifacts:
    - path: "src/mailroom/__main__.py"
      provides: "Conditional poll_completed log level"
      contains: "log.debug"
  key_links: []
---

<objective>
Reduce poll_completed log noise by lowering scheduled/fallback triggers to DEBUG while keeping push triggers at INFO.

Purpose: Production k8s logs are dominated by scheduled poll heartbeats (76/80 lines), burying meaningful triage events. Push-triggered polls indicate real mail activity and should remain visible.
Output: Modified `__main__.py` with conditional log level on poll_completed.
</objective>

<execution_context>
@/Users/flo/.claude/get-shit-done/workflows/execute-plan.md
@/Users/flo/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/mailroom/__main__.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Conditional poll_completed log level</name>
  <files>src/mailroom/__main__.py</files>
  <action>
At line 213 in `src/mailroom/__main__.py`, replace:
```python
log.info("poll_completed", trigger=trigger)
```
with:
```python
if trigger == "push":
    log.info("poll_completed", trigger=trigger)
else:
    log.debug("poll_completed", trigger=trigger)
```

The three trigger values are: "scheduled" (line 186), "push" (line 195), "fallback" (line 203). Only "push" stays at info. No other log statements change.
  </action>
  <verify>
    <automated>cd /Users/flo/Work/Private/Dev/Services/mailroom && python -m pytest tests/ -x -q 2>&1 | tail -5</automated>
  </verify>
  <done>Line 213 uses conditional logging: push triggers log at INFO, scheduled/fallback at DEBUG. All existing tests pass.</done>
</task>

</tasks>

<verification>
- `grep -n "poll_completed" src/mailroom/__main__.py` shows both log.info and log.debug calls
- Full test suite passes
</verification>

<success_criteria>
- push-triggered polls log at INFO level
- scheduled and fallback polls log at DEBUG level
- No other behavior changes
</success_criteria>

<output>
After completion, create `.planning/quick/2-adjust-logging-levels-of-certain-message/2-SUMMARY.md`
</output>
