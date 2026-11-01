"""Load metric points and serve them per metric, oldest first."""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Point:
    at: datetime
    value: float


class MetricStore:
    def __init__(self, points: dict[str, list[Point]] | None = None) -> None:
        self._series: dict[str, list[Point]] = defaultdict(list)
        for name, pts in (points or {}).items():
            self._series[name] = sorted(pts, key=lambda p: p.at)

    @classmethod
    def from_csv(cls, path: Path) -> MetricStore:
        """CSV with columns ``timestamp,metric,value``; timestamps in ISO 8601 with a UTC offset."""
        series: dict[str, list[Point]] = defaultdict(list)
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                at = datetime.fromisoformat(row["timestamp"])
                if at.tzinfo is None:
                    raise ValueError(f"timestamp without timezone: {row['timestamp']}")
                series[row["metric"]].append(Point(at, float(row["value"])))
        return cls(series)

    def time_range(self) -> tuple[datetime, datetime]:
        stamps = [p.at for pts in self._series.values() for p in pts]
        if not stamps:
            raise ValueError("no metric points loaded")
        return min(stamps), max(stamps)

    def up_to(self, metric: str, now: datetime) -> list[Point]:
        return [p for p in self._series.get(metric, []) if p.at <= now]
