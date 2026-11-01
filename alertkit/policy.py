"""Delivery policy: decides whether a fired alert is actually sent right now."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from alertkit.journal import QUIET_HOURS, Journal
from alertkit.models import Rule, Severity


@dataclass
class DeliveryPolicy:
    timezone: str = "UTC"
    quiet_start: time | None = time(22, 0)
    quiet_end: time | None = time(8, 0)
    max_per_day: int = 5

    def in_quiet_hours(self, now: datetime) -> bool:
        if self.quiet_start is None or self.quiet_end is None:
            return False
        local = now.astimezone(ZoneInfo(self.timezone)).time()
        if self.quiet_start <= self.quiet_end:
            return self.quiet_start <= local < self.quiet_end
        return local >= self.quiet_start or local < self.quiet_end     # window wraps past midnight

    def decide(self, rule: Rule, now: datetime, journal: Journal) -> str | None:
        """Return ``None`` to deliver, or the reason the alert is held back.

        Critical alerts bypass quiet hours and the daily cap - those exist to protect
        attention from routine noise, not to hide an outage. Cooldown still applies to
        everything, so one incident does not page every few minutes.
        """
        last = journal.last_delivered(rule.name)
        if last and now - datetime.fromisoformat(last) < timedelta(minutes=rule.cooldown_minutes):
            return f"cooldown ({rule.cooldown_minutes} min)"
        if rule.severity is Severity.CRITICAL:
            return None
        if self.in_quiet_hours(now):
            return QUIET_HOURS
        tz = ZoneInfo(self.timezone)
        day_start = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = journal.delivered_between(day_start.isoformat(), (day_start + timedelta(days=1)).isoformat())
        if sent_today >= self.max_per_day:
            return f"daily cap ({self.max_per_day}) reached"
        return None
