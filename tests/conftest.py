from datetime import datetime, timedelta, timezone

import pytest

from alertkit.series import MetricStore, Point

T0 = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)


def series(*values: float, start: datetime = T0, step_minutes: int = 15) -> list[Point]:
    return [Point(start + timedelta(minutes=step_minutes * i), float(v)) for i, v in enumerate(values)]


@pytest.fixture
def t0() -> datetime:
    return T0


def store(**metrics: list[Point]) -> MetricStore:
    return MetricStore(metrics)
