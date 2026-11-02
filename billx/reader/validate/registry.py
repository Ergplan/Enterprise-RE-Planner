"""The check registry (build prompt 5.4, invariants 2 and 10).

Every check is registered once as a `CheckSpec`: its id, what it `detects` (the smallest
error it catches, which its planted-misread test proves), the paths it `proves` when it is
an equality check, its severity and which bill type it applies to. The function itself
takes `(bill, ctx)` and returns one `CheckResult`; a check whose inputs are missing returns
`skip`, never `pass`. `unverified_inputs` is left empty here: the integrator fills it from
the Values the check's `paths` name.

Paths are schema paths (`meters[2].present`, `line_items[1].amount`, `totals.net_payable`)
and, where `_common.yaml`'s field map gives one, the contract's path beside it
(`energy.kwh` for `energy.gross_kwh`), so the pass rule can find a guaranteed field in
`proves`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from billx.core.schema import Bill, CheckResult, CheckStatus
from billx.reader.identify.profiles import common

if TYPE_CHECKING:
    from billx.reader.identify.profiles import ProfileVersion

Severity = Literal["fail", "warn"]
AppliesTo = Literal["electricity", "gas", "both"]
ProvesSpec = tuple[str, ...] | Callable[[Bill], tuple[str, ...]]

ONE = Decimal(1)
ZERO = Decimal(0)


@dataclass(frozen=True)
class Tolerances:
    """The generic tolerances a profile may loosen (`generic_tolerances`)."""

    qty_x_rate_rel: Decimal = ZERO


@dataclass(frozen=True)
class CheckContext:
    version: ProfileVersion | None = None
    tolerances: Tolerances = Tolerances()
    bill_month: str | None = None

    @classmethod
    def for_version(
        cls, version: ProfileVersion | None, bill_month: str | None = None
    ) -> CheckContext:
        rel = ZERO
        if version is not None:
            rel = Decimal(str(version.generic_tolerances.get("qty_x_rate_rel", 0)))
        return cls(
            version=version, tolerances=Tolerances(qty_x_rate_rel=rel), bill_month=bill_month
        )

    def params(self) -> dict[str, Decimal]:
        if self.version is None:
            return {}
        return self.version.params_for(self.bill_month)


@dataclass(frozen=True)
class CheckSpec:
    id: str
    description: str
    detects: str
    run: Callable[[Bill, CheckContext], CheckResult]
    proves: ProvesSpec = ()
    equality: bool = False
    severity: Severity = "fail"
    applies_to: AppliesTo = "electricity"
    order: int = field(default=0, compare=False)

    def applies(self, bill_type: str) -> bool:
        return self.applies_to == "both" or self.applies_to == bill_type

    def declared_proves(self, bill: Bill) -> tuple[str, ...]:
        return self.proves(bill) if callable(self.proves) else self.proves


_REGISTRY: dict[str, CheckSpec] = {}


def register(spec: CheckSpec) -> CheckSpec:
    if spec.id in _REGISTRY:
        raise ValueError(f"check {spec.id} registered twice")
    _REGISTRY[spec.id] = spec
    return spec


def check(
    id: str,
    description: str,
    *,
    detects: str,
    proves: ProvesSpec = (),
    equality: bool = False,
    severity: Severity = "fail",
    applies_to: AppliesTo = "electricity",
) -> Callable[
    [Callable[[Bill, CheckContext], CheckResult]], Callable[[Bill, CheckContext], CheckResult]
]:
    """Decorator: register the function as the one implementation of check `id`."""

    def deco(fn: Callable[[Bill, CheckContext], CheckResult]):
        register(
            CheckSpec(
                id=id,
                description=description,
                detects=detects,
                run=fn,
                proves=proves,
                equality=equality,
                severity=severity,
                applies_to=applies_to,
                order=len(_REGISTRY),
            )
        )
        return fn

    return deco


def registered() -> tuple[CheckSpec, ...]:
    """Every registered check, in id order (G01.. G20, GG01.., S.., T..)."""
    return tuple(sorted(_REGISTRY.values(), key=lambda s: _sort_key(s.id)))


def spec(check_id: str) -> CheckSpec:
    return _REGISTRY[check_id]


def _sort_key(check_id: str) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", check_id)
    if m:
        return (m.group(1), int(m.group(2)), "")
    return (check_id.split(":")[0], 10**6, check_id)


# building results ---------------------------------------------------------------------------


def result(
    spec_or_id: CheckSpec | str,
    status: CheckStatus,
    *,
    expected: Decimal | str | None = None,
    actual: Decimal | str | None = None,
    tolerance: Decimal | str | None = None,
    paths: tuple[str, ...] = (),
    proves: tuple[str, ...] | None = None,
    note: str | None = None,
    description: str | None = None,
    detects: str | None = None,
    equality: bool | None = None,
) -> CheckResult:
    """A CheckResult from a spec: strings for every number, the spec's `detects`, and, for an
    equality check, the paths it proves (the declared ones unless the check narrows them)."""
    s = _REGISTRY[spec_or_id] if isinstance(spec_or_id, str) else spec_or_id
    eq = s.equality if equality is None else equality
    pv: tuple[str, ...] = ()
    if eq:
        pv = tuple(dict.fromkeys(proves if proves is not None else paths))
    return CheckResult(
        id=s.id,
        description=description or s.description,
        status=status,
        expected=fmt(expected),
        actual=fmt(actual),
        tolerance=fmt(tolerance),
        paths=tuple(dict.fromkeys(paths)),
        detects=detects or s.detects,
        proves=pv,
        equality=eq,
        note=note,
    )


def skip(spec_or_id: CheckSpec | str, note: str, paths: tuple[str, ...] = ()) -> CheckResult:
    return result(spec_or_id, "skip", note=note, paths=paths)


def fmt(x: Decimal | str | int | None) -> str | None:
    if x is None:
        return None
    if isinstance(x, str):
        return x
    if isinstance(x, bool) or isinstance(x, float):
        raise TypeError("checks carry Decimal values only")
    d = Decimal(x) if isinstance(x, int) else x
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def within(actual: Decimal, expected: Decimal, tolerance: Decimal) -> bool:
    return abs(actual - expected) <= tolerance


def verdict(ok: bool, severity: Severity) -> CheckStatus:
    if ok:
        return "pass"
    return "fail" if severity == "fail" else "warn"


# paths -------------------------------------------------------------------------------------


def _reverse_field_map(bill_type: str) -> dict[str, tuple[str, ...]]:
    gas_only = {
        "consumer.customer_id",
        "readings.previous",
        "readings.current",
        "volume.scm",
        "gas.gcv_kcal_per_scm",
        "energy.mmbtu",
        "totals.amount",
    }
    out: dict[str, list[str]] = {}
    for contract_path, schema_path in (common().get("field_map") or {}).items():
        if "[" in schema_path:
            continue
        is_gas = contract_path in gas_only
        if (bill_type == "gas") != is_gas and contract_path != "totals.net_payable":
            continue
        if bill_type == "gas" and contract_path == "totals.net_payable":
            continue
        out.setdefault(schema_path, []).append(contract_path)
    return {k: tuple(v) for k, v in out.items()}


def paths_for(bill: Bill, *schema_paths: str) -> tuple[str, ...]:
    """Schema paths plus the contract paths the field map gives them, deduplicated."""
    rev = _reverse_field_map(bill.bill_type)
    out: list[str] = []
    for p in schema_paths:
        out.append(p)
        out.extend(c for c in rev.get(p, ()) if c != p)
    return tuple(dict.fromkeys(out))


def meter_path(i: int, attr: str) -> str:
    return f"meters[{i}].{attr}"


def line_path(i: int, attr: str = "amount") -> str:
    return f"line_items[{i}].{attr}"


def energy_path(quantity: str) -> str | None:
    return {"kWh": "energy.gross_kwh", "kVAh": "energy.gross_kvah"}.get(quantity)


__all__ = [
    "ONE",
    "ZERO",
    "AppliesTo",
    "CheckContext",
    "CheckSpec",
    "Severity",
    "Tolerances",
    "check",
    "energy_path",
    "fmt",
    "line_path",
    "meter_path",
    "paths_for",
    "register",
    "registered",
    "result",
    "skip",
    "spec",
    "verdict",
    "within",
]
