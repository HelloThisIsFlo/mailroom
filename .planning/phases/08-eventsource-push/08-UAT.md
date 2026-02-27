---
status: diagnosed
phase: 08-eventsource-push
source: 08-01-SUMMARY.md, 08-02-SUMMARY.md
started: 2026-02-27T12:00:00Z
updated: 2026-02-27T12:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Config defaults updated
expected: Run `python -c "from mailroom.core.config import MailroomSettings; s = MailroomSettings(); print(s.debounce_seconds, s.poll_interval)"`. Output shows `3 60` (debounce_seconds=3, poll_interval=60).
result: pass

### 2. Health endpoint includes EventSource status
expected: Start the service and hit `/healthz`. Response JSON should include an `eventsource` object with fields: `connected`, `last_event`, `reconnect_count`, `url`, and `error`.
result: pass

### 3. SSE listener starts on service boot
expected: Start the service (`python -m mailroom`). Logs should show the SSE listener thread starting and attempting to connect to the EventSource URL from the JMAP session.
result: issue
reported: "the shutdown signal takes a bit to be acted upon — Ctrl+C at 11:31:46, service_stopped at 11:32:01. queue.get(timeout=poll_interval) blocks up to 60s and shutdown signal doesn't wake it."
severity: minor

### 4. Push-triggered triage (low latency)
expected: With the service running, send a test email. Triage should happen within a few seconds (pushed by SSE state change event) rather than waiting for the full 60s poll interval. Log entry should show `trigger=push`.
result: pass

### 5. Fallback polling when SSE unavailable
expected: If the SSE connection is unavailable or drops, the service should still poll at the regular `poll_interval` (60s). Log entries for these polls should show `trigger=fallback`.
result: pass

### 6. Human integration test runs
expected: Run `python human-tests/test_16_eventsource_push.py`. The script should execute and test push-triggered triage latency against the real Fastmail account.
result: issue
reported: "The feature itself works (proven by service logs), but the test's automated monitoring just shows a stream of POLL DETECTED lines without distinguishing push-triggered triages from regular polling or detecting when a new triage actually happened."
severity: major

## Summary

total: 6
passed: 4
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "Service shuts down promptly when receiving SIGINT/SIGTERM"
  status: failed
  reason: "User reported: shutdown signal takes a bit to be acted upon — queue.get(timeout=poll_interval) blocks up to 60s and shutdown signal doesn't wake it"
  severity: minor
  test: 3
  root_cause: "queue.Queue.get(timeout=poll_interval) at __main__.py:175 blocks up to 60s. Signal handler sets shutdown_event but nothing wakes the blocking get(). The shutdown check at line 188-189 only runs after get() returns."
  artifacts:
    - path: "src/mailroom/__main__.py"
      issue: "queue.get(timeout=poll_interval) not interruptible by shutdown signal"
  missing:
    - "Push sentinel (None) into event_queue from signal handler so queue.get() unblocks immediately"

- truth: "Human test 16 effectively detects and reports push-triggered triage events"
  status: failed
  reason: "User reported: test runs but monitoring just shows POLL DETECTED stream without distinguishing push vs fallback or detecting actual triage events"
  severity: major
  test: 6
  root_cause: "/healthz does not expose last_poll_trigger field. Main loop tracks trigger=push|fallback but never writes it to HealthHandler. Test monitors last_poll_age_seconds which fires on every check within the age window, not once per discrete poll event."
  artifacts:
    - path: "src/mailroom/__main__.py"
      issue: "trigger variable not written to HealthHandler; no last_poll_trigger in health JSON"
    - path: "human-tests/test_16_eventsource_push.py"
      issue: "Monitoring uses age threshold instead of discrete event detection"
  missing:
    - "Add HealthHandler.last_poll_trigger class attribute, write it alongside last_successful_poll"
    - "Expose last_poll_trigger in /healthz JSON response"
    - "Rewrite test monitoring to detect discrete poll events (timestamp change) and read trigger field"

- truth: "SSE unit tests run without excessive real-time waits slowing the test suite"
  status: failed
  reason: "User reported: some eventsource tests seem to use real wait time, making the whole test suite way slower. Consider simulating time if it doesn't hurt coverage or add too much complexity."
  severity: minor
  test: 0
  root_cause: "Two tests trigger exponential backoff via 500 errors: test_sse_reconnects_on_error (2.02s) and test_sse_updates_health_on_disconnect (2.03s). Both hit shutdown_event.wait(delay) at eventsource.py:117 with delay=2s (min(2^1, 60)). No seam exists to inject a fake clock."
  artifacts:
    - path: "tests/test_eventsource.py"
      issue: "test_sse_reconnects_on_error and test_sse_updates_health_on_disconnect each block 2s on real backoff"
    - path: "src/mailroom/eventsource.py"
      issue: "No injectable sleep_fn parameter — delay computed inline and passed to blocking OS call"
  missing:
    - "Add sleep_fn parameter to sse_listener (default: shutdown_event.wait), tests pass lambda t: None to skip real waits"
