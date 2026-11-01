"""Generate the example metrics: two days of a web service with one incident.

Day 2 contains: a nightly job that stops sending heartbeats for two hours, and an
afternoon incident where latency and errors spike while signups drop.
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
STEP = timedelta(minutes=15)


def main() -> None:
    rng = random.Random(7)
    rows = []
    t = START
    while t < START + timedelta(days=2):
        day2 = t - START >= timedelta(days=1)
        incident = day2 and 13 <= t.hour < 15
        hour_factor = 0.4 + 0.6 * (8 <= t.hour < 22)  # quieter at night
        rows.append((t, "latency_p95_ms", round(rng.gauss(900 if incident else 180, 25), 1)))
        rows.append((t, "error_rate_pct", round(max(0.0, rng.gauss(6.0 if incident else 0.4, 0.15)), 2)))
        signups = rng.gauss(20 * hour_factor * (0.3 if incident else 1.0), 2)
        rows.append((t, "signups", max(0, round(signups))))
        if not (day2 and 3 <= t.hour < 5):     # nightly job silent for two hours
            rows.append((t, "job_heartbeat", 1))
        t += STEP
    out = Path(__file__).with_name("metrics.csv")
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "metric", "value"])
        w.writerows((ts.isoformat(), m, v) for ts, m, v in rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
