from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


Op = Literal[">", ">=", "<", "<="]


class Rule(BaseModel):
    """One alert rule. ``kind`` decides how the checked value is computed.

    - ``threshold``: the latest value compared with ``value``
    - ``pct_change``: mean of the last ``window`` points vs a baseline, in percent. The baseline is
      the ``window`` points before (``previous_window``) or the same period 24 hours earlier
      (``same_time_yesterday``), which ignores normal daily rhythm such as quiet nights
    - ``absence``: fires when the newest point is older than ``window`` minutes
    """

    name: str = Field(pattern=r"^[a-z0-9_-]+$")
    metric: str
    kind: Literal["threshold", "pct_change", "absence"]
    op: Op = ">"
    value: float = 0.0
    window: int = Field(default=1, ge=1)
    baseline: Literal["previous_window", "same_time_yesterday"] = "previous_window"
    severity: Severity = Severity.WARNING
    cooldown_minutes: int = Field(default=60, ge=0)
    description: str = ""


@dataclass(frozen=True)
class Evaluation:
    """The outcome of checking one rule once - recorded whether or not it fired.

    Built only through the two constructors below, so a check that could not run
    (not enough history) is never confused with a check that ran and passed.
    """

    rule: str
    checked_at: datetime
    fired: bool
    computed_value: float | None
    threshold: float
    insufficient_history: bool
    detail: str

    @classmethod
    def checked(cls, rule: Rule, at: datetime, value: float, fired: bool, detail: str) -> Evaluation:
        return cls(rule.name, at, fired, value, rule.value, False, detail)

    @classmethod
    def no_data(cls, rule: Rule, at: datetime, detail: str) -> Evaluation:
        return cls(rule.name, at, False, None, rule.value, True, detail)


@dataclass(frozen=True)
class Decision:
    evaluation: Evaluation
    rule: Rule
    delivered: bool
    suppressed_reason: str | None = None
