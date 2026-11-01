"""Message formatting and delivery channels."""
from __future__ import annotations

import math
import os
from typing import Protocol

import httpx

from alertkit.models import Decision, Severity

_ICON = {Severity.INFO: "[info]", Severity.WARNING: "[warning]", Severity.CRITICAL: "[CRITICAL]"}


def format_message(decision: Decision) -> str:
    """Build the alert text. A line that would need a number we do not have is left out
    entirely rather than printed as 'None', 'nan' or '0' - a wrong number is worse than none."""
    e, rule = decision.evaluation, decision.rule
    lines = [f"{_ICON[rule.severity]} {rule.name}: {rule.description or rule.metric}"]
    if e.computed_value is not None and math.isfinite(e.computed_value):
        unit = "%" if rule.kind == "pct_change" else (" min" if rule.kind == "absence" else "")
        lines.append(f"value {e.computed_value:.4g}{unit} {rule.op} threshold {rule.value:g}{unit}")
    if e.detail:
        lines.append(e.detail)
    lines.append(f"at {e.checked_at.isoformat(timespec='minutes')}")
    return "\n".join(lines)


def format_digest(held: list[dict]) -> str:
    """One summary of everything quiet hours held back, so a night-time problem that
    resolved itself before morning is still reported instead of silently dropped."""
    lines = ["While quiet hours were on:"]
    for h in held:
        first, last = h["first"][11:16], h["last"][11:16]
        span = first if first == last else f"{first}-{last} UTC"
        peak = f", peak {h['max_value']:.4g}" if h["max_value"] is not None else ""
        lines.append(f"- {h['rule']}: fired {h['times']}x ({span}{peak})")
    return "\n".join(lines)


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class ConsoleNotifier:
    def send(self, text: str) -> None:
        print(text, end="\n\n")


class SlackWebhookNotifier:
    def __init__(self, url: str | None = None, client: httpx.Client | None = None) -> None:
        self.url = url or os.environ["SLACK_WEBHOOK_URL"]
        self.client = client or httpx.Client(timeout=10)

    def send(self, text: str) -> None:
        self.client.post(self.url, json={"text": text}).raise_for_status()


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None, client: httpx.Client | None = None):
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
        self.client = client or httpx.Client(timeout=10)

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.client.post(url, json={"chat_id": self.chat_id, "text": text}).raise_for_status()
