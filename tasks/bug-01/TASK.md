# TASK: Range off-by-one boundary exclusion

## Environment
- Base repo: arrow-py/arrow @ 2224255c4acc594d734cef0bbc83360452a67983
- Language/runtime: Python 3.11
- Test command: `pytest tests/ -x -q`

## Problem statement (what the model will see)
When calling `Arrow.range()` with a specified `end` parameter, the final item of the range is omitted if the step span exactly divides the range (i.e. if the last step lands precisely on the `end` datetime). For instance, `Arrow.range('day', arrow.get('2013-01-01'), arrow.get('2013-01-03'))` returns only `2013-01-01` and `2013-01-02` instead of including `2013-01-03`.

## Success criteria
- `pytest tests/ -x -q` exits 0
- No previously-passing test may now fail (PASS_TO_PASS check)
- The newly-failing test(s) must now pass (FAIL_TO_PASS check)

## Hidden gold fix (NEVER shown to the audited model/agent)
- File(s) changed: `arrow/arrow.py`
- Diff:
```diff
--- a/arrow/arrow.py
+++ b/arrow/arrow.py
@@ -489,3 +489,3 @@ class Arrow:
-        while current < end and i < limit:
+        while current <= end and i < limit:
             i += 1
```
- Why this is the minimal correct fix: Restores the inclusive boundary check `current <= end` ensuring the exact endpoint of the range is yielded.

## Difficulty calibration notes
- Expected difficulty: easy
- Why: The bug is located directly in the loop condition of `Arrow.range()`. The test failure points clearly to `range()` returning one fewer element than expected.
