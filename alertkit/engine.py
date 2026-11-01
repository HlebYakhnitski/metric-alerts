from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import yaml

from alertkit.evaluator import evaluate
from alertkit.journal import Journal
from alertkit.models import Decision, Rule
from alertkit.notifiers import Notifier, format_digest, format_message
from alertkit.policy import DeliveryPolicy
from alertkit.series import MetricStore

log = logging.getLogger(__name__)


def load_rules(path: Path) -> list[Rule]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = [Rule(**item) for item in data["rules"]]
    names = [r.name for r in rules]
    if len(names) != len(set(names)):
        raise ValueError("rule names must be unique")
    return rules


def run_once(
    rules: list[Rule],
    store: MetricStore,
    journal: Journal,
    policy: DeliveryPolicy,
    notifiers: list[Notifier],
    now: datetime,
) -> list[Decision]:
    """Evaluate every rule, journal every result, and deliver what the policy allows.

    Alerts held by quiet hours are not dropped: the first run after quiet hours end
    sends one digest of them. A failing notifier is logged and does not stop the
    other rules or channels.
    """
    if not policy.in_quiet_hours(now):
        held = journal.held_for_quiet_hours_since(journal.last_digest())
        if held:
            _broadcast(notifiers, format_digest(held), "digest")
            journal.record_digest(now.isoformat())

    decisions = []
    for rule in rules:
        evaluation = evaluate(rule, store, now)
        reason = policy.decide(rule, now, journal) if evaluation.fired else None
        decision = Decision(evaluation, rule, delivered=evaluation.fired and reason is None, suppressed_reason=reason)
        if decision.delivered:
            _broadcast(notifiers, format_message(decision), rule.name)
        journal.record(decision)
        decisions.append(decision)
    return decisions


def _broadcast(notifiers: list[Notifier], text: str, label: str) -> None:
    for notifier in notifiers:
        try:
            notifier.send(text)
        except Exception:
            log.exception("notifier %s failed for %s", type(notifier).__name__, label)
