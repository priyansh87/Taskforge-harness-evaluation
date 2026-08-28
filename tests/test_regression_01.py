import pytest
import arrow
from datetime import datetime

def test_regression_range_exact_end():
    start = datetime(2013, 1, 1)
    end = datetime(2013, 1, 3)
    result = list(arrow.Arrow.range("day", start, end))
    assert len(result) == 3
    assert result[-1] == arrow.get(end)
