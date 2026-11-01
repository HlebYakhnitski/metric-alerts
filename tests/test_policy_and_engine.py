from datetime import datetime, time, timedelta, timezone

import httpx

from alertkit.engine import load_rules, run_once
from alertkit.journal import Journal
from alertkit.models import Decision, Evaluation, Rule, Severity
from alertkit.notifiers import SlackWebhookNotifier, TelegramNotifier, format_message
from alertkit.policy import DeliveryPolicy
from tests.conftest import series, store

NOON = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
NIGHT = datetime(2026, 3, 2, 23, 30, tzinfo=timezone.utc)


class Collect:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


class Broken:
    def send(self, text: str) -> None:
        raise RuntimeError("channel down")


def high(sev: Severity = Severity.WARNING, cooldown: int = 60) -> Rule:
    return Rule(name="high", metric="m", kind="threshold", op=">", value=10, severity=sev, cooldown_minutes=cooldown)


def always_high():
    return store(m=series(*([50] * 200), start=NOON - timedelta(days=1)))


def test_quiet_hours_wrap_midnight():
    p = DeliveryPolicy("UTC", time(22), time(8))
    assert p.in_quiet_hours(NIGHT)
    assert p.in_quiet_hours(NIGHT.replace(hour=3))
    assert not p.in_quiet_hours(NOON)


def test_quiet_hours_respect_timezone():
    p = DeliveryPolicy("Europe/Warsaw", time(22), time(8))
    assert p.in_quiet_hours(datetime(2026, 3, 2, 21, 30, tzinfo=timezone.utc))   # 22:30 in Warsaw


def test_cooldown_suppresses_repeats():
    j, out = Journal(), Collect()
    rules, s, p = [high(cooldown=60)], always_high(), DeliveryPolicy("UTC", None, None)
    first = run_once(rules, s, j, p, [out], NOON)
    second = run_once(rules, s, j, p, [out], NOON + timedelta(minutes=15))
    third = run_once(rules, s, j, p, [out], NOON + timedelta(minutes=61))
    assert [first[0].delivered, second[0].delivered, third[0].delivered] == [True, False, True]
    assert second[0].suppressed_reason.startswith("cooldown")


def test_critical_bypasses_quiet_hours_but_warning_does_not():
    p = DeliveryPolicy("UTC", time(22), time(8))
    assert run_once([high(Severity.CRITICAL)], always_high(), Journal(), p, [], NIGHT)[0].delivered
    warn = run_once([high(Severity.WARNING)], always_high(), Journal(), p, [], NIGHT)[0]
    assert not warn.delivered and warn.suppressed_reason == "quiet hours"


def test_daily_cap():
    j, p = Journal(), DeliveryPolicy("UTC", None, None, max_per_day=2)
    rules = [high(cooldown=0)]
    delivered = [run_once(rules, always_high(), j, p, [], NOON + timedelta(minutes=15 * i))[0].delivered
                 for i in range(4)]
    assert delivered == [True, True, False, False]


def test_held_alerts_are_sent_as_digest_after_quiet_hours():
    j, out, p = Journal(), Collect(), DeliveryPolicy("UTC", time(22), time(8))
    rules, s = [high()], always_high()
    run_once(rules, s, j, p, [out], NIGHT)
    run_once(rules, s, j, p, [out], NIGHT + timedelta(hours=1))
    assert out.sent == []                                  # held overnight
    morning = NIGHT.replace(hour=8, minute=15) + timedelta(days=1)
    run_once(rules, s, j, p, [out], morning)
    assert out.sent[0].startswith("While quiet hours were on:")
    assert "high: fired 2x" in out.sent[0]
    run_once(rules, s, j, p, [out], morning + timedelta(minutes=15))
    assert sum(m.startswith("While quiet") for m in out.sent) == 1   # digest sent once


def test_every_evaluation_is_journaled_including_non_fires():
    j = Journal()
    rules = [high(), Rule(name="low", metric="m", kind="threshold", op="<", value=0)]
    run_once(rules, always_high(), j, DeliveryPolicy("UTC", None, None), [], NOON)
    summary = {r["rule"]: r for r in j.summary()}
    assert summary["low"]["checks"] == 1 and summary["low"]["fired"] == 0
    assert summary["high"]["fired"] == 1


def test_broken_notifier_does_not_block_others():
    out = Collect()
    run_once([high()], always_high(), Journal(), DeliveryPolicy("UTC", None, None), [Broken(), out], NOON)
    assert len(out.sent) == 1


def test_message_never_prints_a_missing_number():
    r = high()
    e = Evaluation.no_data(r, NOON, "no points yet")
    text = format_message(Decision(e, r, delivered=True))
    assert "None" not in text and "nan" not in text and "threshold" not in text


def test_slack_and_telegram_payloads():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.read().decode()))
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    SlackWebhookNotifier("https://hooks.example/abc", client).send("hello")
    TelegramNotifier("T0K", "42", client).send("hi")
    assert seen[0] == ("https://hooks.example/abc", '{"text":"hello"}')
    assert seen[1][0] == "https://api.telegram.org/botT0K/sendMessage" and '"chat_id":"42"' in seen[1][1]


def test_example_rules_load(tmp_path):
    from pathlib import Path

    rules = load_rules(Path(__file__).parent.parent / "examples" / "rules.yaml")
    assert {r.name for r in rules} == {"latency-high", "error-rate-critical", "signups-drop", "nightly-job-silent"}
