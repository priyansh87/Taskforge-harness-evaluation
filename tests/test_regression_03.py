import pytest
import arrow

def test_regression_timestamp_precision():
    ts = 1609459200.123456
    a = arrow.get(ts)
    assert a.microsecond == 123456
