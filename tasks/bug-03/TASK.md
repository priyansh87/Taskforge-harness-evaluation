# TASK: Utility normalize_timestamp precision truncation

## Environment
- Base repo: arrow-py/arrow @ 2224255c4acc594d734cef0bbc83360452a67983
- Language/runtime: Python 3.11
- Test command: `pytest tests/ -x -q`

## Problem statement (what the model will see)
When parsing or creating an `Arrow` object from a floating-point timestamp that contains sub-second precision (such as milliseconds or microseconds, e.g., `1609459200.123456`), the sub-second components are silently lost and set to `0`. This occurs during instantiation using timestamps and affects any logic converting timestamps to `Arrow` objects.

## Success criteria
- `pytest tests/ -x -q` exits 0
- No previously-passing test may now fail (PASS_TO_PASS check)
- The newly-failing test(s) must now pass (FAIL_TO_PASS check)

## Hidden gold fix (NEVER shown to the audited model/agent)
- File(s) changed: `arrow/util.py`
- Diff:
```diff
--- a/arrow/util.py
+++ b/arrow/util.py
@@ -70,2 +70,2 @@
-def normalize_timestamp(timestamp: float) -> int:
+def normalize_timestamp(timestamp: float) -> float:
@@ -79,2 +79,2 @@
-    return int(timestamp)
+    return timestamp
```
- Why this is the minimal correct fix: Restores the float type return from `normalize_timestamp`, ensuring sub-second (microsecond) components are not truncated to integers.

## Difficulty calibration notes
- Expected difficulty: hard
- Why: The bug is located in a helper utility function (`normalize_timestamp` in `arrow/util.py`) that resides in a different file from the main `Arrow` class (`arrow/arrow.py`). Since returning an integer is still a valid type for timestamps, it does not trigger any type errors or traceback crashes, resulting in silent data truncation. A model must trace through file boundaries and inspect variable types to discover it.
