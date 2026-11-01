"""Replay a metrics file through the rules, step by step, as a scheduler would.

    python -m alertkit.cli replay --rules examples/rules.yaml --metrics examples/metrics.csv
"""
from __future__ import annotations

import argparse
from datetime import time, timedelta
from pathlib import Path

from alertkit.engine import load_rules, run_once
from alertkit.journal import Journal
from alertkit.notifiers import ConsoleNotifier
from alertkit.policy import DeliveryPolicy
from alertkit.series import MetricStore


def _hhmm(value: str) -> time:
    return time.fromisoformat(value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    rp = sub.add_parser("replay")
    rp.add_argument("--rules", type=Path, required=True)
    rp.add_argument("--metrics", type=Path, required=True)
    rp.add_argument("--step-minutes", type=int, default=15)
    rp.add_argument("--journal", default=":memory:")
    rp.add_argument("--timezone", default="Europe/Warsaw")
    rp.add_argument("--quiet", nargs=2, type=_hhmm, default=[time(22), time(8)], metavar=("START", "END"))
    rp.add_argument("--max-per-day", type=int, default=5)
    args = parser.parse_args(argv)

    rules = load_rules(args.rules)
    store = MetricStore.from_csv(args.metrics)
    journal = Journal(args.journal)
    policy = DeliveryPolicy(args.timezone, args.quiet[0], args.quiet[1], args.max_per_day)

    start, end = store.time_range()
    now, step = start, timedelta(minutes=args.step_minutes)
    delivered = suppressed = 0
    while now <= end:
        for d in run_once(rules, store, journal, policy, [ConsoleNotifier()], now):
            delivered += d.delivered
            suppressed += d.evaluation.fired and not d.delivered
        now += step

    print(f"replayed {start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} | delivered {delivered}, suppressed {suppressed}\n")
    print(f"{'rule':<22}{'checks':>8}{'fired':>8}{'no data':>9}{'held':>7}{'min':>10}{'mean':>10}{'max':>10}")
    for row in journal.summary():
        def fmt(v):
            return "-" if v is None else f"{v:.3g}"
        print(f"{row['rule']:<22}{row['checks']:>8}{row['fired']:>8}{row['no_data']:>9}{row['suppressed']:>7}"
              f"{fmt(row['min']):>10}{fmt(row['mean']):>10}{fmt(row['max']):>10}")


if __name__ == "__main__":
    main()
