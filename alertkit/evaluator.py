"""Compute the checked value for a rule and decide whether it fires."""
from __future__ import annotations

import operator
from datetime import datetime, timedelta
from statistics import fmean

from alertkit.models import Evaluation, Rule
from alertkit.series import MetricStore

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


def evaluate(rule: Rule, store: MetricStore, now: datetime) -> Evaluation:
    points = store.up_to(rule.metric, now)
    compare = _OPS[rule.op]

    if rule.kind == "absence":
        if not points:
            return Evaluation.checked(rule, now, float("inf"), True, "no data has ever been received")
        age = (now - points[-1].at) / timedelta(minutes=1)
        return Evaluation.checked(rule, now, age, age > rule.window, f"last point {age:.0f} min ago")

    if rule.kind == "threshold":
        if not points:
            return Evaluation.no_data(rule, now, "no points yet")
        latest = points[-1].value
        return Evaluation.checked(rule, now, latest, compare(latest, rule.value), "")

    # pct_change: mean of the latest window against a baseline window
    if len(points) < rule.window:
        return Evaluation.no_data(rule, now, f"need {rule.window} points, have {len(points)}")
    window = points[-rule.window :]
    recent = fmean(p.value for p in window)
    if rule.baseline == "previous_window":
        if len(points) < 2 * rule.window:
            return Evaluation.no_data(rule, now, f"need {2 * rule.window} points, have {len(points)}")
        base_points = points[-2 * rule.window : -rule.window]
    else:
        day = timedelta(days=1)
        lo, hi = window[0].at - day, window[-1].at - day
        base_points = [p for p in points if lo <= p.at <= hi]
        if not base_points:
            return Evaluation.no_data(rule, now, "no data for the same period yesterday")
    previous = fmean(p.value for p in base_points)
    if previous == 0:
        return Evaluation.no_data(rule, now, "previous period averaged zero; percent change undefined")
    change = (recent - previous) / abs(previous) * 100
    detail = f"{previous:g} -> {recent:g} ({change:+.1f}%)"
    return Evaluation.checked(rule, now, change, compare(change, rule.value), detail)
