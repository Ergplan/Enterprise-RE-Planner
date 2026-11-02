"""The pass rule (build prompt 5.2): from the Values and the check results to `passed`,
`status`, `review_reasons`, `flags`, `accepted` and `accepted_by`. It assigns no
verification (decide() did that); it only reads them.
"""

from __future__ import annotations

from dataclasses import dataclass

from billx.core.schema import CheckResult, Value


@dataclass(frozen=True)
class Verdict:
    passed: bool
    status: str
    review_reasons: tuple[str, ...]
    flags: tuple[str, ...]
    accepted: bool
    accepted_by: str | None
    failed_checks: tuple[str, ...]


def _value_by_path(values: list[Value]) -> dict[str, Value]:
    return {v.path: v for v in values}


def verdict(
    values: list[Value],
    checks: list[CheckResult],
    *,
    required: list[str],
    energy_paths: tuple[str, ...],
    money_path: str,
    either_required: dict[str, str] | None = None,
    accept_confirmed: bool = True,
) -> Verdict:
    """Apply the five conditions of 5.2 and the printed-inconsistency rule.

    `required` are the contract's required paths; `either_required` maps a required path to
    the alternative that satisfies it (energy.kwh -> energy.kvah under 1.1; volume.scm <->
    energy.mmbtu for gas). `energy_paths` and `money_path` are the fields that must take
    part in a passing equality check (condition 3).
    """
    either_required = either_required or {}
    by_path = _value_by_path(values)
    reasons: list[str] = []
    flags: list[str] = []
    confirmed_any = False

    def ok(path: str) -> bool:
        v = by_path.get(path)
        return v is not None and v.value is not None and v.verification in ("verified", "confirmed")

    # 2. required fields present and verified (or confirmed)
    for path in required:
        if ok(path):
            if by_path[path].verification == "confirmed":
                confirmed_any = True
            continue
        alt = either_required.get(path)
        if alt and ok(alt):
            if by_path[alt].verification == "confirmed":
                confirmed_any = True
            continue
        v = by_path.get(path)
        if v is None or v.value is None:
            reasons.append(f"required_field_not_printed:{path}")
        elif v.verification == "disputed":
            reasons.append(f"disputed:{path}")
        else:
            reasons.append(f"unverified:{path}")

    # 5. every other field that carries a value is verified
    for v in values:
        if v.path in required or v.value is None:
            continue
        if v.verification == "confirmed":
            confirmed_any = True
        elif v.verification == "disputed":
            reasons.append(f"disputed:{v.path}")
        elif v.verification != "verified":
            reasons.append(f"unverified:{v.path}")

    # 1 and 4. checks: a failing check with every input verified is a printed inconsistency
    failed: list[str] = []
    for c in checks:
        if c.status == "fail":
            if c.unverified_inputs:
                failed.append(c.id)
                reasons.append(f"check_failed:{c.id}")
                reasons.extend(f"unverified:{p}" for p in c.unverified_inputs)
            else:
                failed.append(c.id)
                flags.append(f"printed_inconsistency:{c.id}")
        elif c.status == "skip" and c.unverified_inputs:
            reasons.extend(f"unverified:{p}" for p in c.unverified_inputs)

    # 3. arithmetic covers the money and the energy: a passing equality check, or one that
    # failed on fully verified inputs (a printed inconsistency: the arithmetic ran and tied
    # the values; the bill itself is wrong, and it is flagged above)
    covering = [
        c
        for c in checks
        if c.equality and (c.status == "pass" or (c.status == "fail" and not c.unverified_inputs))
    ]
    covered = {p for c in covering for p in c.proves}
    energy_ok = any(
        by_path.get(p) is not None and by_path[p].value is not None and p in covered
        for p in energy_paths
    )
    money_ok = money_path in covered
    if not (energy_ok and money_ok):
        reasons.append("insufficient_arithmetic")

    reasons = list(dict.fromkeys(reasons))
    flags = list(dict.fromkeys(flags))
    if reasons:
        return Verdict(
            False, "needs_review", tuple(reasons), tuple(flags), False, None, tuple(failed)
        )
    if confirmed_any:
        accepted = accept_confirmed
        return Verdict(
            False,
            "confirmed",
            (),
            tuple(flags),
            accepted,
            "human" if accepted else None,
            tuple(failed),
        )
    return Verdict(True, "passed", (), tuple(flags), True, "engine", tuple(failed))
