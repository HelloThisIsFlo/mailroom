---
phase: quick-5
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mailroom/core/logging.py
  - tests/test_logging.py
autonomous: true
requirements: [TODO-13]
must_haves:
  truths:
    - "JSON log output has timestamp as the first field"
    - "JSON log output has level as the second field"
    - "JSON log output has component as the third field (when present)"
    - "JSON log output has event as the next key field"
    - "Remaining context fields follow in arbitrary order"
    - "Console (TTY) logging is unaffected"
  artifacts:
    - path: "src/mailroom/core/logging.py"
      provides: "reorder_keys processor function"
      contains: "def reorder_keys"
    - path: "tests/test_logging.py"
      provides: "Test for field ordering in JSON output"
      contains: "test_json_field_order"
  key_links:
    - from: "reorder_keys processor"
      to: "structlog processor chain"
      via: "inserted before JSONRenderer in shared_processors"
      pattern: "reorder_keys.*JSONRenderer"
---

<objective>
Add a structlog processor that reorders JSON log fields for scannability.

Purpose: When scanning raw JSON logs (kubectl logs, docker logs), having a consistent field order with timestamp/level/component/event first makes logs much easier to read at a glance.

Output: Updated logging.py with reorder_keys processor, updated test file with ordering verification.
</objective>

<execution_context>
@/Users/flo/.claude/get-shit-done/workflows/execute-plan.md
@/Users/flo/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/mailroom/core/logging.py
@tests/test_logging.py
</context>

<interfaces>
<!-- Key types and contracts the executor needs. -->

From src/mailroom/core/logging.py:
```python
def configure_logging(log_level: str = "info") -> None: ...
def get_logger(**initial_context: object) -> structlog.stdlib.BoundLogger: ...
```

structlog processor signature:
```python
def processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    # Must return event_dict (or a new dict)
```

Current processor chain (prod/JSON path):
```python
shared_processors = [add_log_level, TimeStamper(fmt="iso", utc=True), format_exc_info]
# Then for non-TTY: append dict_tracebacks, renderer = JSONRenderer()
# Final: processors=[*shared_processors, renderer]
```
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add reorder_keys processor and test field ordering</name>
  <files>src/mailroom/core/logging.py, tests/test_logging.py</files>
  <behavior>
    - Test: JSON output field order starts with timestamp, level, then event (and component when bound)
    - Test: With bound component context, order is timestamp -> level -> component -> event -> remaining
    - Test: Without component, order is timestamp -> level -> event -> remaining
    - Test: All original fields are preserved (no data loss)
    - Test: reorder_keys processor unit test with raw event_dict input
  </behavior>
  <action>
    1. In tests/test_logging.py, add test_json_field_order:
       - Configure JSON logging, bind component="test", emit a log with extra fields
       - Parse JSON output, get list(data.keys())
       - Assert first keys are ["timestamp", "level", "component", "event"] in that order
       - Assert all extra fields are still present

    2. Add test_reorder_keys_processor as a unit test:
       - Call reorder_keys directly with a sample event_dict containing timestamp, level, event, component, and extra keys
       - Assert list(result.keys()) starts with the priority keys
       - Assert all values preserved

    3. In src/mailroom/core/logging.py, add reorder_keys function:
       ```python
       _PRIORITY_KEYS = ("timestamp", "level", "component", "event")

       def reorder_keys(
           logger: object, method_name: str, event_dict: dict[str, object]
       ) -> dict[str, object]:
           """Reorder event_dict so priority fields come first for scannable JSON."""
           ordered: dict[str, object] = {}
           for key in _PRIORITY_KEYS:
               if key in event_dict:
                   ordered[key] = event_dict[key]
           for key, value in event_dict.items():
               if key not in ordered:
                   ordered[key] = value
           return ordered
       ```

    4. Insert reorder_keys into the processor chain for the JSON path only:
       - Add it to shared_processors AFTER dict_tracebacks but BEFORE JSONRenderer
       - Specifically, in the non-TTY branch, after `shared_processors.append(structlog.processors.dict_tracebacks)`, add `shared_processors.append(reorder_keys)`
       - Do NOT add it to the TTY/console path (ConsoleRenderer handles its own formatting)
  </action>
  <verify>
    <automated>cd /Users/flo/Work/Private/Dev/Services/mailroom && python -m pytest tests/test_logging.py -x -v</automated>
  </verify>
  <done>
    - reorder_keys processor exists and is tested in isolation
    - JSON log output has fields in order: timestamp, level, [component if present], event, ...remaining
    - All existing tests still pass
    - Console/TTY logging path is unchanged
  </done>
</task>

</tasks>

<verification>
```bash
# All logging tests pass
python -m pytest tests/test_logging.py -x -v

# Quick smoke test: JSON output has correct field order
python -c "
import sys, json
from io import StringIO
from unittest.mock import patch

buf = StringIO()
buf.isatty = lambda: False

with patch.object(sys, 'stderr', buf):
    from mailroom.core.logging import configure_logging
    import structlog
    configure_logging('info')
    log = structlog.get_logger(component='test')
    log.info('smoke_check', extra_field='value')

data = json.loads(buf.getvalue().strip())
keys = list(data.keys())
print('Field order:', keys)
assert keys[0] == 'timestamp', f'Expected timestamp first, got {keys[0]}'
assert keys[1] == 'level', f'Expected level second, got {keys[1]}'
assert keys[2] == 'component', f'Expected component third, got {keys[2]}'
assert keys[3] == 'event', f'Expected event fourth, got {keys[3]}'
print('PASS: Field ordering correct')
"
```
</verification>

<success_criteria>
- JSON log fields appear in order: timestamp, level, component (when present), event, ...rest
- All existing logging tests pass unchanged
- New test explicitly verifies field ordering
- Console/dev logging unaffected
</success_criteria>

<output>
After completion, create `.planning/quick/5-reorder-json-log-fields-for-scannability/5-SUMMARY.md`
</output>
