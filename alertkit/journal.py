"""Append-only SQLite journal of every evaluation, including the ones that did not fire.

Fired alerts alone cannot tell you whether a threshold is well placed: you also need
how often the value came close and how often the check could not run at all. Those
rows cannot be reconstructed later, so they are written from the first run.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from alertkit.models import Decision

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    rule                 TEXT NOT NULL,
    checked_at           TEXT NOT NULL,
    computed_value       REAL,
    threshold            REAL NOT NULL,
    fired                INTEGER NOT NULL,
    insufficient_history INTEGER NOT NULL,
    delivered            INTEGER NOT NULL,
    suppressed_reason    TEXT,
    detail               TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_rule_time ON evaluations (rule, checked_at);
CREATE TABLE IF NOT EXISTS digests (sent_at TEXT NOT NULL);
"""

QUIET_HOURS = "quiet hours"


class Journal:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)

    def record(self, decision: Decision) -> None:
        e = decision.evaluation
        value = e.computed_value if e.computed_value is None or e.computed_value != float("inf") else None
        with self.db:
            self.db.execute(
                "INSERT INTO evaluations (rule, checked_at, computed_value, threshold, fired, insufficient_history,"
                " delivered, suppressed_reason, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e.rule, e.checked_at.isoformat(), value, e.threshold, int(e.fired), int(e.insufficient_history),
                 int(decision.delivered), decision.suppressed_reason, e.detail),
            )

    def summary(self) -> list[dict]:
        """Per rule: checks run, fire rate, how often it could not run, how often delivery was suppressed."""
        rows = self.db.execute(
            """
            SELECT rule,
                   COUNT(*)                                            AS checks,
                   SUM(fired)                                          AS fired,
                   SUM(insufficient_history)                           AS no_data,
                   SUM(fired AND NOT delivered)                        AS suppressed,
                   MIN(computed_value), AVG(computed_value), MAX(computed_value)
            FROM evaluations GROUP BY rule ORDER BY rule
            """
        ).fetchall()
        keys = ["rule", "checks", "fired", "no_data", "suppressed", "min", "mean", "max"]
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def last_delivered(self, rule: str) -> str | None:
        row = self.db.execute(
            "SELECT MAX(checked_at) FROM evaluations WHERE rule = ? AND delivered = 1", (rule,)
        ).fetchone()
        return row[0]

    def delivered_between(self, start_iso: str, end_iso: str) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM evaluations WHERE delivered = 1 AND checked_at >= ? AND checked_at < ?",
            (start_iso, end_iso),
        ).fetchone()
        return row[0]

    def held_for_quiet_hours_since(self, since_iso: str) -> list[dict]:
        """Alerts that fired but were held back by quiet hours after ``since_iso``, grouped by rule."""
        rows = self.db.execute(
            """
            SELECT rule, COUNT(*), MIN(checked_at), MAX(checked_at), MAX(computed_value)
            FROM evaluations
            WHERE fired = 1 AND delivered = 0 AND suppressed_reason = ? AND checked_at > ?
            GROUP BY rule ORDER BY MIN(checked_at)
            """,
            (QUIET_HOURS, since_iso),
        ).fetchall()
        keys = ["rule", "times", "first", "last", "max_value"]
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def last_digest(self) -> str:
        row = self.db.execute("SELECT MAX(sent_at) FROM digests").fetchone()
        return row[0] or "0001-01-01T00:00:00+00:00"

    def record_digest(self, sent_at_iso: str) -> None:
        with self.db:
            self.db.execute("INSERT INTO digests (sent_at) VALUES (?)", (sent_at_iso,))
