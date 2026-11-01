# metric-alerts

Rule-based alerting for metric time series — the kind that pages you when p95 latency jumps or a nightly job goes silent — designed around two ideas:

1. **Record every check, not just the alerts.** You can only tell whether a threshold is well placed if you know how often the value came close, and how often the check could not run at all. Those rows cannot be reconstructed later.
2. **Protect attention without hiding problems.** Quiet hours, cooldowns and a daily cap stop routine noise — but nothing held back is thrown away.

```
$ python -m alertkit.cli replay --rules examples/rules.yaml --metrics examples/metrics.csv

[CRITICAL] error-rate-critical: more than 5% of requests failing
value 5.99 > threshold 5
at 2026-03-03T13:00+00:00

While quiet hours were on:
- nightly-job-silent: fired 5x (03:45-04:45 UTC, peak 120)

rule                    checks   fired  no data   held       min      mean       max
error-rate-critical        192       8        0      4      0.01     0.644      6.27
latency-high               192       8        0      6       112       211       927
nightly-job-silent         192       5        0      5         0      2.81       120
signups-drop               192       6       96      5     -69.6     -6.64      26.9
```

## Rules

```yaml
rules:
  - name: error-rate-critical
    metric: error_rate_pct
    kind: threshold            # latest value vs threshold
    op: ">"
    value: 5
    severity: critical         # bypasses quiet hours and the daily cap
    cooldown_minutes: 30

  - name: signups-drop
    metric: signups
    kind: pct_change           # mean of the last `window` points vs a baseline
    op: "<"
    value: -50
    window: 4
    baseline: same_time_yesterday

  - name: nightly-job-silent
    metric: job_heartbeat
    kind: absence              # fires when the newest point is older than `window` minutes
    window: 45
```

Rules are validated with Pydantic on load; names must be unique.

## Two problems the example data exposed

The example is two days of a synthetic web service with one incident. Replaying it found two flaws in the first version of the engine, both fixed:

**Quiet hours were dropping alerts, not deferring them.** The nightly job stopped sending heartbeats from 04:00 to 06:00 Warsaw time. The rule fired five times — all inside quiet hours, all held back — and by 08:00 the job had recovered. Nobody would ever have heard about it. Now the first run after quiet hours end sends one digest of everything that was held.

**Hour-on-hour comparison fired every evening.** Signups fall naturally at night, so "this hour vs the previous hour" raised a false alarm on every ramp-down. Comparing with the same hour yesterday removed all three false alarms while still catching the incident — at a cost the journal makes visible: the rule cannot run for the first 24 hours (`no data: 96`) instead of pretending everything is fine.

## Design

```
alertkit/
  models.py     Rule (validated), Evaluation, Decision
  series.py     metric points from CSV, served "as of" a point in time
  evaluator.py  threshold / pct_change / absence
  policy.py     cooldown, quiet hours (timezone-aware, wraps midnight), daily cap
  journal.py    SQLite: every evaluation, fire rates per rule, quiet-hours digest
  notifiers.py  console, Slack webhook, Telegram; message formatting
  engine.py     one evaluation cycle
  cli.py        replay a metrics file as a scheduler would
```

- **"Could not check" is not "passed".** An `Evaluation` can only be built through `checked(...)` or `no_data(...)`, so missing history is recorded as such rather than as a quiet non-fire.
- **No number, no line.** If a value is missing, the message leaves that line out instead of printing `None`, `nan` or a misleading `0`.
- **Critical alerts skip quiet hours and the cap** — those exist to filter routine noise, not to hide an outage. Cooldown still applies to everything.
- **One broken channel does not block the rest.** A failing notifier is logged and the cycle continues.
- **Replay before you deploy.** The CLI steps through historical data exactly as a scheduler would, so a new rule's fire rate is known before it pages anyone.

## Usage

```bash
pip install -e ".[dev]"
python examples/generate_metrics.py          # regenerate the example data (deterministic)
python -m alertkit.cli replay --rules examples/rules.yaml --metrics examples/metrics.csv
```

Options: `--timezone`, `--quiet 22:00 08:00`, `--max-per-day`, `--step-minutes`, `--journal path.db` to keep the history.

Delivery channels read `SLACK_WEBHOOK_URL`, or `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. To run on a schedule, call `run_once` from cron or any job runner with the current time.

## Tests

```bash
pytest
```

25 tests: every rule kind including missing history and undefined baselines, operators, quiet hours across midnight and time zones, cooldown, the daily cap, critical bypass, the digest being sent exactly once, journaling of non-fires, notifier isolation, message formatting, and Slack/Telegram payloads against a mocked HTTP transport.

## License

MIT
