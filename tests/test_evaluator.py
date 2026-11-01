from datetime import timedelta

import pytest
from pydantic import ValidationError

from alertkit.evaluator import evaluate
from alertkit.models import Rule
from tests.conftest import T0, series, store


def rule(**kw) -> Rule:
    base = {"name": "r", "metric": "m", "kind": "threshold", "op": ">", "value": 10}
    return Rule(**{**base, **kw})


def test_threshold_fires_on_latest_value():
    s = store(m=series(5, 50, 12))
    e = evaluate(rule(), s, T0 + timedelta(hours=1))
    assert e.fired and e.computed_value == 12


def test_threshold_ignores_future_points():
    s = store(m=series(5, 50))
    assert not evaluate(rule(), s, T0).fired          # only the first point exists at T0


def test_threshold_without_data_is_no_data_not_pass():
    e = evaluate(rule(), store(), T0)
    assert e.insufficient_history and not e.fired and e.computed_value is None


@pytest.mark.parametrize("op, value, expected", [(">=", 12, True), ("<", 12, False), ("<=", 12, True)])
def test_operators(op, value, expected):
    assert evaluate(rule(op=op, value=value), store(m=series(12)), T0).fired is expected


def test_pct_change_previous_window():
    s = store(m=series(100, 100, 40, 40))
    e = evaluate(rule(kind="pct_change", op="<", value=-50, window=2), s, T0 + timedelta(hours=1))
    assert e.computed_value == pytest.approx(-60) and e.fired


def test_pct_change_needs_two_windows():
    e = evaluate(rule(kind="pct_change", window=2), store(m=series(1, 2, 3)), T0 + timedelta(hours=1))
    assert e.insufficient_history


def test_pct_change_zero_baseline_is_undefined():
    e = evaluate(rule(kind="pct_change", window=1), store(m=series(0, 5)), T0 + timedelta(hours=1))
    assert e.insufficient_history and "undefined" in e.detail


def test_same_time_yesterday_ignores_daily_rhythm():
    # yesterday evening was quiet too, so a quiet evening today is not a drop
    yesterday = series(10, 10, start=T0)
    today = series(10, 10, start=T0 + timedelta(days=1))
    s = store(m=yesterday + today)
    r = rule(kind="pct_change", op="<", value=-50, window=2, baseline="same_time_yesterday")
    e = evaluate(r, s, T0 + timedelta(days=1, minutes=15))
    assert e.computed_value == pytest.approx(0) and not e.fired


def test_same_time_yesterday_without_history():
    r = rule(kind="pct_change", window=2, baseline="same_time_yesterday")
    e = evaluate(r, store(m=series(5, 5)), T0 + timedelta(minutes=15))
    assert e.insufficient_history


def test_absence_fires_after_window():
    s = store(m=series(1))
    r = rule(kind="absence", window=45)
    assert not evaluate(r, s, T0 + timedelta(minutes=30)).fired
    assert evaluate(r, s, T0 + timedelta(minutes=60)).fired


def test_absence_with_no_data_ever_fires():
    assert evaluate(rule(kind="absence", window=10), store(), T0).fired


def test_rule_validation():
    with pytest.raises(ValidationError):
        rule(name="Has Spaces")
    with pytest.raises(ValidationError):
        rule(window=0)
    with pytest.raises(ValidationError):
        rule(op="!=")
