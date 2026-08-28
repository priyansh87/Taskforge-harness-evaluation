import pytest
import arrow
from datetime import datetime

def test_regression_span_bounds():
    a = arrow.get(datetime(2013, 2, 15, 3, 30))
    # Default bounds is "[)" which means floor is inclusive (no shift) and ceil is exclusive (shifted by -1 ms)
    floor, ceil = a.span("hour")
    assert floor.microsecond == 0
    assert ceil.microsecond == 999999
