# TASK: Span bounds inclusive/exclusive logic swap

## Environment
- Base repo: arrow-py/arrow @ 2224255c4acc594d734cef0bbc83360452a67983
- Language/runtime: Python 3.11
- Test command: `pytest tests/ -x -q`

## Problem statement (what the model will see)
When calling `Arrow.span()` with standard bounds specifiers, the inclusion and exclusion behaviors are inverted. A bracket `[` (which should be inclusive, meaning no shift) is treated as exclusive (shifting the floor boundary forward by 1 microsecond), while a parenthesis `(` is treated as inclusive. Similarly, `]` (inclusive) is treated as exclusive (shifting the ceiling boundary back by 1 microsecond), and `)` is treated as inclusive.

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
@@ -590,2 +590,2 @@ class Arrow:
-        if bounds[0] == "[":
+        if bounds[0] == "(":
             floor = floor.shift(microseconds=+1)
@@ -593,2 +593,2 @@ class Arrow:
-        if bounds[1] == "]":
+        if bounds[1] == ")":
             ceil = ceil.shift(microseconds=-1)
```
- Why this is the minimal correct fix: Corrects the boundary checking logic to properly check for open boundaries `(` and `)` rather than closed boundaries `[` and `]`.

## Difficulty calibration notes
- Expected difficulty: medium
- Why: The bounds parsing logic is inside the `span` method, and although it's easy to trace, a model might confuse the logic if it doesn't carefully read the meaning of parentheses vs brackets.
