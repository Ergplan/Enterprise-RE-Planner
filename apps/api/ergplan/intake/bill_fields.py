"""The fields ergPLAN takes from a billx bill (master prompt 8.3), read from billx's field objects
into Decimals with their verification. Nothing here reads a PDF."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

PATHS = (
    "utility.name",
    "tariff.category",
    "connection.tariff_category",
    "consumer.account_number",
    "consumer.name",
    "period.from",
    "period.to",
    "period.bill_month",
    "demand.contract_kva",
    "demand.max_kva",
    "energy.kwh",
    "energy.kvah",
    "energy.billed_units",
    "energy.power_factor",
    "charges.energy",
    "charges.demand",
    "open_access.re_kwh",
    "open_access.non_re_kwh",
    "open_access.banked_kwh",
    "net_metering.import_kwh",
    "net_metering.export_kwh",
    "green_tariff.kwh",
    "totals.current_charges",
    "totals.net_payable",
    "totals.due_date_rebate",
)
ACCEPTING = {"verified", "confirmed"}


@dataclass
class FieldValue:
    path: str
    value: Any
    unit: str | None
    verification: str | None
    page: int | None

    @property
    def trusted(self) -> bool:
        return self.verification in ACCEPTING


@dataclass
class BillFacts:
    index: int
    status: str
    accepted: bool
    accepted_by: str | None
    profile_id: str | None
    review_reasons: list[str]
    fields: dict[str, FieldValue] = field(default_factory=dict)
    tod: list[dict[str, Any]] = field(default_factory=list)
    charges_by_code: list[dict[str, Any]] = field(default_factory=list)

    def num(self, path: str) -> Decimal | None:
        f = self.fields.get(path)
        return to_dec(f.value) if f else None

    def text(self, path: str) -> str | None:
        f = self.fields.get(path)
        return None if f is None or f.value is None else str(f.value)

    @property
    def bill_month(self) -> date | None:
        return parse_month(self.text("period.bill_month")) or parse_month(self.text("period.to"))

    @property
    def energy_kwh_equiv(self) -> tuple[Decimal | None, str]:
        """The month's consumption: kWh when printed, else kVAh (the unit says which)."""
        kwh = self.num("energy.kwh")
        if kwh is not None:
            return kwh, "kWh"
        return self.num("energy.kvah"), "kVAh"


def to_dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        return None


def parse_month(v: str | None) -> date | None:
    """'2026-05', '2026-05-31', 'May-2026', 'MAY 26' → the first of that month."""
    if not v:
        return None
    s = v.strip()
    m = re.match(r"^(\d{4})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    m = re.match(r"^([A-Za-z]{3})[A-Za-z]*[\s\-/']*(\d{2,4})$", s)
    if m and m.group(1).lower() in months:
        y = int(m.group(2))
        return date(y + 2000 if y < 100 else y, months.index(m.group(1).lower()) + 1, 1)
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), 1)
    return None


def _walk(fields: dict[str, Any], path: str) -> Any:
    node: Any = fields
    for p in path.split("."):
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    return node


def facts(bill: dict[str, Any]) -> BillFacts:
    f = bill.get("fields") or {}
    out = BillFacts(
        index=int(bill.get("index", 0)),
        status=str(bill.get("status") or ("passed" if bill.get("passed") else "needs_review")),
        accepted=bool(bill.get("accepted", bill.get("passed", False))),
        accepted_by=bill.get("accepted_by"),
        profile_id=(bill.get("profile") or {}).get("id"),
        review_reasons=list(bill.get("review_reasons") or []),
    )
    for p in PATHS:
        node = _walk(f, p)
        if isinstance(node, dict) and "value" in node:
            out.fields[p] = FieldValue(
                p, node.get("value"), node.get("unit"), node.get("verification"), node.get("page")
            )
    tod = _walk(f, "energy.tod")
    if isinstance(tod, list):
        for row in tod:
            slot = (row.get("slot") or {}) if isinstance(row, dict) else {}
            kwh = (row.get("kwh") or {}) if isinstance(row, dict) else {}
            out.tod.append(
                {
                    "slot": slot.get("value") if isinstance(slot, dict) else slot,
                    "kwh": to_dec(kwh.get("value") if isinstance(kwh, dict) else kwh),
                    "unit": kwh.get("unit") if isinstance(kwh, dict) else None,
                    "verification": kwh.get("verification") if isinstance(kwh, dict) else None,
                    "page": kwh.get("page") if isinstance(kwh, dict) else None,
                }
            )
    by_code = _walk(f, "charges.by_code")
    if isinstance(by_code, list):
        for row in by_code:
            code = row.get("code") if isinstance(row, dict) else None
            amt = row.get("amount") if isinstance(row, dict) else None
            out.charges_by_code.append(
                {
                    "code": code.get("value") if isinstance(code, dict) else code,
                    "amount": to_dec(amt.get("value") if isinstance(amt, dict) else amt),
                }
            )
    return out


def from_result(result: dict[str, Any]) -> list[BillFacts]:
    return [facts(b) for b in result.get("bills", [])]
