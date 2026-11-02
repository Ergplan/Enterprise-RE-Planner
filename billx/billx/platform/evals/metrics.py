"""The metrics of build prompt section 8, per layout x input kind x route, always with n.

- **Silent errors:** a field `verified` on a passed bill whose normalised value differs from
  the truth (both sides through `billx.core.normalize.normalise` with the field's type from
  `config/guaranteed_fields.yaml`), with the rule-of-three upper bound 3/n when none is seen.
- **Coverage:** passed bills / readable bills submitted.
- **Correct refusals:** non-bills refused (not a bill, unreadable, wrong type); never an
  error. **False refusals:** bills refused or classed as another type; always an error.
  A bill declined as `model_not_allowed` or `budget_exceeded` is neither: it is counted as
  declined, because the caller chose that.
- **Accuracy over attempted, per field,** on passed bills: of the fields that carry a value,
  the share whose normalised value equals the truth.
- **Formula coverage:** the share of elements whose formula recheck is `match` or `differs`.
- **Planted misreads:** caught when the declared check reports `fail`, else missed. Planted
  cases take part in no other metric: their page really prints the planted number.
- **Cost and time per bill:** median and 95th percentile (nearest rank), Decimal.

Nothing here keeps a value: only counts, case ids, field paths and check ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from math import ceil
from typing import TYPE_CHECKING

from billx.core.normalize import normalise
from billx.core.settings import load_config
from billx.platform.evals.manifest import BILL_TYPES, EvalCase

if TYPE_CHECKING:
    from billx.core.schema import BillResult, Envelope

REFUSED = ("unreadable", "not_a_bill", "wrong_document_type")
DECLINED = ("model_not_allowed", "budget_exceeded")
ATTEMPTED = ("passed", "confirmed", "needs_review")
GroupKey = tuple[str, str, str]  # layout, input kind, route
ALL: GroupKey = ("all", "all", "all")
_COST = Decimal("0.0001")
_SECONDS = Decimal("0.001")
_RATE = Decimal("0.0001")


def field_types() -> dict[str, dict[str, str]]:
    """{electricity|gas: {path: type}} for the scalar guaranteed fields."""
    cfg = load_config("guaranteed_fields.yaml")
    return {
        kind: {f["path"]: f["type"] for f in cfg[kind] if f["type"] != "array"}
        for kind in ("electricity", "gas")
    }


def rule_of_three(n: int) -> Decimal | None:
    """With zero errors in n, the true rate is below about 3/n with 95% confidence."""
    if n <= 0:
        return None
    return (Decimal(3) / Decimal(n)).quantize(_RATE, ROUND_CEILING)


def percentile(values: list[Decimal], p: Decimal, places: Decimal) -> Decimal | None:
    """Nearest-rank percentile (p in 0..1) of exact decimals."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, ceil(p * len(ordered)))
    return ordered[rank - 1].quantize(places, ROUND_HALF_UP)


def median(values: list[Decimal], places: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    return mid.quantize(places, ROUND_HALF_UP)


def _ratio(num: int, den: int) -> Decimal | None:
    return None if den == 0 else (Decimal(num) / Decimal(den)).quantize(_RATE, ROUND_HALF_UP)


@dataclass
class Outcome:
    """One case's result, reduced to what the metrics need."""

    case: EvalCase
    route: str
    status: str  # a BillResult status, or "no_bills", "error"
    read_as: str | None  # the engine's document type for the bill it read, or None
    passed: bool
    seconds: Decimal
    cost_usd: Decimal
    silent_errors: list[str] = field(default_factory=list)  # field paths
    attempted: dict[str, bool] = field(default_factory=dict)  # path -> correct, on passed bills
    elements: int = 0
    elements_computable: int = 0
    planted_caught: bool | None = None  # None: not a planted case
    error: str | None = None  # exception class name only

    @property
    def refused(self) -> bool:
        return self.status in REFUSED or self.status == "no_bills"

    @property
    def declined(self) -> bool:
        return self.status in DECLINED

    @property
    def classed_as_other_type(self) -> bool:
        return self.read_as is not None and self.read_as != self.case.document_type


def _bill_of(envelope: Envelope) -> BillResult | None:
    """The bill result the metrics judge: the first electricity or gas bill, else the first."""
    for b in envelope.bills:
        if b.document_type in BILL_TYPES:
            return b
    return envelope.bills[0] if envelope.bills else None


def outcome(
    case: EvalCase,
    envelope: Envelope | None,
    seconds: Decimal,
    error: str | None,
    types: dict[str, dict[str, str]],
) -> Outcome:
    """Reduce one case's envelope to an Outcome; values are compared here and dropped."""
    cost = sum((u.cost_usd for u in envelope.usage), Decimal(0)) if envelope else Decimal(0)
    if envelope is None:
        return Outcome(case, "none", "error", None, False, seconds, cost, error=error or "error")
    bill = _bill_of(envelope)
    if bill is None:
        return Outcome(case, "none", "no_bills", None, False, seconds, cost)
    out = Outcome(case, bill.route, bill.status, bill.document_type, bill.passed, seconds, cost)
    for b in envelope.bills:
        out.elements += len(b.elements)
        out.elements_computable += sum(
            1 for e in b.elements if e.formula_recheck.status in ("match", "differs")
        )
    if case.planted is not None:
        out.planted_caught = any(
            c.id == case.planted.check and c.status == "fail"
            for b in envelope.bills
            for c in b.checks
        )
        return out
    kind = case.field_kind
    if kind is None or not bill.passed or bill.document_type != case.document_type:
        return out
    by_type = types[kind]
    for v in bill.fields:
        if v.path not in case.truth or v.path not in by_type or v.value is None:
            continue
        truth = case.truth[v.path]
        want = normalise(truth, by_type[v.path]) if truth is not None else None
        got = normalise(v.value, by_type[v.path])
        if v.path == "utility.name" and want and got and (want in got or got in want):
            got = want  # the name as printed may carry the short code, or be it
        correct = got is not None and got == want
        out.attempted[v.path] = correct
        if v.verification == "verified" and not correct:
            out.silent_errors.append(v.path)
    return out


@dataclass
class GroupMetrics:
    """Counts for one layout x input kind x route (or the whole set)."""

    key: GroupKey
    n: int = 0
    bills: int = 0
    non_bills: int = 0
    planted: int = 0
    passed: int = 0
    needs_review: int = 0
    declined: int = 0
    errors: int = 0
    silent_errors: int = 0
    silent_error_paths: list[tuple[str, str]] = field(default_factory=list)  # (case id, path)
    correct_refusals: int = 0
    false_refusals: int = 0
    false_refusal_ids: list[str] = field(default_factory=list)
    non_bills_read_as_bills: int = 0
    non_bills_read_as_bills_ids: list[str] = field(default_factory=list)
    field_correct: dict[str, int] = field(default_factory=dict)
    field_attempted: dict[str, int] = field(default_factory=dict)
    elements: int = 0
    elements_computable: int = 0
    planted_caught: int = 0
    planted_missed: int = 0
    planted_missed_ids: list[tuple[str, str]] = field(default_factory=list)  # (case id, check)
    error_ids: list[tuple[str, str]] = field(default_factory=list)  # (case id, error class)
    costs: list[Decimal] = field(default_factory=list)
    seconds: list[Decimal] = field(default_factory=list)

    def add(self, o: Outcome) -> None:
        self.n += 1
        self.costs.append(o.cost_usd)
        self.seconds.append(o.seconds)
        if o.error is not None:
            self.errors += 1
            self.error_ids.append((o.case.id, o.error))
        if o.case.planted is not None:
            self.planted += 1
            if o.planted_caught:
                self.planted_caught += 1
            else:
                self.planted_missed += 1
                self.planted_missed_ids.append((o.case.id, o.case.planted.check))
            return
        self.elements += o.elements
        self.elements_computable += o.elements_computable
        if o.case.is_bill:
            self.bills += 1
            if o.error is not None:
                return
            if o.refused or o.classed_as_other_type:
                self.false_refusals += 1
                self.false_refusal_ids.append(o.case.id)
            elif o.declined:
                self.declined += 1
            elif o.passed:
                self.passed += 1
            else:
                self.needs_review += 1
            for path in o.silent_errors:
                self.silent_errors += 1
                self.silent_error_paths.append((o.case.id, path))
            for path, correct in o.attempted.items():
                self.field_attempted[path] = self.field_attempted.get(path, 0) + 1
                self.field_correct[path] = self.field_correct.get(path, 0) + int(correct)
        else:
            self.non_bills += 1
            if o.error is not None:
                return
            if o.read_as in BILL_TYPES and not o.refused:
                self.non_bills_read_as_bills += 1
                self.non_bills_read_as_bills_ids.append(o.case.id)
            else:
                self.correct_refusals += 1

    # derived ----------------------------------------------------------------------------

    @property
    def coverage(self) -> Decimal | None:
        return _ratio(self.passed, self.bills)

    @property
    def silent_error_bound(self) -> Decimal | None:
        """3/n over passed bills, only when no silent error was seen."""
        return rule_of_three(self.passed) if self.silent_errors == 0 else None

    @property
    def formula_coverage(self) -> Decimal | None:
        return _ratio(self.elements_computable, self.elements)

    def field_accuracy(self) -> dict[str, tuple[int, int, Decimal | None]]:
        return {
            path: (self.field_correct[path], n, _ratio(self.field_correct[path], n))
            for path, n in sorted(self.field_attempted.items())
        }

    @property
    def cost_median(self) -> Decimal | None:
        return median(self.costs, _COST)

    @property
    def cost_p95(self) -> Decimal | None:
        return percentile(self.costs, Decimal("0.95"), _COST)

    @property
    def seconds_median(self) -> Decimal | None:
        return median(self.seconds, _SECONDS)

    @property
    def seconds_p95(self) -> Decimal | None:
        return percentile(self.seconds, Decimal("0.95"), _SECONDS)


@dataclass
class Metrics:
    total: GroupMetrics
    groups: dict[GroupKey, GroupMetrics]

    @property
    def all_planted_caught(self) -> bool:
        return self.total.planted_missed == 0


def compute(outcomes: list[Outcome]) -> Metrics:
    total = GroupMetrics(ALL)
    groups: dict[GroupKey, GroupMetrics] = {}
    for o in outcomes:
        key: GroupKey = (o.case.layout, o.case.input_kind, o.route)
        groups.setdefault(key, GroupMetrics(key)).add(o)
        total.add(o)
    return Metrics(total, dict(sorted(groups.items())))
