"""What a bill says about the connection beyond its figures: which DISCOM supplies it, in which state,
and whether the consumer already takes open-access power (and of what kind), each finding with the
bill page it rests on; and which approved settlement rules the next stage will apply for that state.

The DISCOM comes from billx's layout profile, else from the DISCOM's name as the bill prints it. The
open-access arrangement is read from what the bill prints: open-access units set off (per slot or in
total), banked units, open-access charge lines with an amount (wheeling, cross-subsidy and additional
surcharge, transmission, banking) and green-tariff units or premium; its kind (captive, group
captive, third party, exchange, GEOA) only from words the bill prints. What the bill does not say is
left for the client to state. No model is called here: this reads billx's stored result."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.sourced import RefKind, SourceRef
from ..db.models import Bill, Jurisdiction, RulebookVersion
from ..rulebook import repository
from ..rulebook.service import UnknownJurisdiction
from . import bills as bill_store
from . import defaults

OpenAccess = Literal["none_seen", "open_access", "green_tariff"]
OWNERSHIPS = ("captive", "group_captive", "third_party")
OWNERSHIP_LABEL = {
    "captive": "Captive",
    "group_captive": "Group captive",
    "third_party": "Third-party open access",
}

# charge lines that only an open-access consumer pays
OA_CODES = {
    "wheeling_charge": "wheeling charges",
    "cross_subsidy_surcharge": "cross-subsidy surcharge",
    "additional_surcharge": "additional surcharge",
    "transmission_charge": "transmission charges",
    "open_access_banking": "banking charges",
}
# words that name the kind of open access, as bills print them
KIND_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("group_captive", re.compile(r"(?i)\bgroup\s*captive\b")),
    ("captive", re.compile(r"(?i)(?<!group )\bcaptive\b|\bCPP\b")),
    ("third_party", re.compile(r"(?i)\bthird[\s-]*party\b|\b3rd\s*party\b")),
    ("exchange", re.compile(r"(?i)\b(IEX|PXIL|HPX|power\s*exchange|exchange\s*units?)\b")),
    ("geoa", re.compile(r"(?i)\bGEOA\b|green\s*energy\s*open\s*access")),
)
KIND_LABEL = {
    "captive": "captive",
    "group_captive": "group captive",
    "third_party": "third party",
    "exchange": "power exchange",
    "geoa": "green energy open access (GEOA)",
}


class Evidence(BaseModel):
    finding: str
    ref: SourceRef


class SettlementRoute(BaseModel):
    """The settlement rule the next stage applies for one ownership, or why there is none."""

    ownership: str
    ownership_label: str
    rule_label: str | None
    rulebook: str | None  # the approved version's title (the regulation it was read from)
    version: int | None
    ref: SourceRef | None


class Recognition(BaseModel):
    discom: str | None
    discom_name: str | None
    discom_how: str | None  # how the DISCOM was recognised, in words
    discom_ref: SourceRef | None
    state: str | None
    state_name: str | None
    open_access: OpenAccess
    open_access_kinds: list[str]
    evidence: list[Evidence]
    settlement: list[SettlementRoute]
    notes: list[str]


@dataclass(frozen=True)
class _Found:
    discom: str | None
    how: str | None
    ref: SourceRef | None


def _ref(bill: Bill, path: str, page: Any) -> SourceRef:
    return SourceRef(
        kind=RefKind.BILL,
        bill_id=bill.id,
        field_path=path,
        page=page if isinstance(page, int) and page > 0 else None,
    )


def _walk(tree: Any, path: str) -> Any:
    node = tree
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _num(node: Any) -> Decimal | None:
    raw = node.get("value") if isinstance(node, dict) else node
    if raw is None:
        return None
    try:
        return Decimal(str(raw).replace(",", ""))
    except InvalidOperation:
        return None


def _bill_dict(bill: Bill) -> dict[str, Any]:
    for b in (bill.billx_result or {}).get("bills", []):
        if int(b.get("index", 0)) == bill.bill_index:
            return dict(b)
    return {}


def discom_of(bill: Bill) -> _Found:
    """billx's layout profile first; else the DISCOM's printed name (utility.name)."""
    pid = bill_store.profile_id(bill)
    from_profile = defaults.discom_from_profile(pid)
    if from_profile:
        return _Found(from_profile, f"billx's layout profile for {from_profile.upper()}", None)
    node = _walk(_bill_dict(bill).get("fields") or {}, "utility.name")
    printed = node.get("value") if isinstance(node, dict) else None
    by_name = defaults.discom_from_name(printed)
    if by_name:
        return _Found(
            by_name, "the DISCOM's name printed on the bill", _ref(bill, "utility.name", node.get("page"))
        )
    return _Found(None, None, None)


def _open_access(bill: Bill, b: dict[str, Any]) -> tuple[OpenAccess, list[str], list[Evidence]]:
    fields = b.get("fields") or {}
    evidence: list[Evidence] = []
    texts: list[tuple[str, SourceRef]] = []
    oa_seen = False
    for path, finding in (
        ("open_access.re_kwh", "renewable open-access or captive units set off"),
        ("open_access.non_re_kwh", "other open-access units set off"),
        ("open_access.banked_kwh", "banked units drawn"),
    ):
        node = _walk(fields, path)
        v = _num(node)
        if v is not None and v != 0:
            oa_seen = True
            unit = (node.get("unit") if isinstance(node, dict) else None) or "kWh"
            evidence.append(
                Evidence(
                    finding=f"{finding}: {node.get('printed') or v} {unit}",
                    ref=_ref(bill, path, node.get("page")),
                )
            )
    slots = [
        (i, item)
        for i, item in enumerate(_walk(fields, "energy.tod") or [])
        if isinstance(item, dict) and (_num(item.get("open_access")) or 0) != 0
    ]
    if slots:
        oa_seen = True
        i, item = slots[0]
        node = item["open_access"]
        evidence.append(
            Evidence(
                finding=f"open-access units set off in {len(slots)} time-of-day slot"
                + ("s" if len(slots) > 1 else ""),
                ref=_ref(bill, f"energy.tod.{i}.open_access", node.get("page")),
            )
        )
    green = False
    gnode = _walk(fields, "green_tariff.kwh")
    if (_num(gnode) or 0) != 0:
        green = True
        evidence.append(
            Evidence(
                finding="units billed under the green tariff",
                ref=_ref(bill, "green_tariff.kwh", gnode.get("page")),
            )
        )
    for e in b.get("elements") or []:
        if not isinstance(e, dict):
            continue
        amount = e.get("amount")
        label = str(e.get("label") or "")
        ref = _ref(
            bill,
            f"elements[{e.get('index')}].amount",
            amount.get("page") if isinstance(amount, dict) else None,
        )
        texts.append((label, ref))
        if (_num(amount) or 0) == 0:
            continue
        code = e.get("code")
        if code in OA_CODES:
            oa_seen = True
            evidence.append(Evidence(finding=f"{OA_CODES[code]} charged ('{label}')", ref=ref))
        elif code == "green_tariff_premium":
            green = True
            evidence.append(Evidence(finding=f"green tariff premium charged ('{label}')", ref=ref))
    for item_i, item in enumerate(_walk(fields, "energy.tod") or []):
        slot = item.get("slot") if isinstance(item, dict) else None
        text = slot.get("value") if isinstance(slot, dict) else slot
        if text:
            texts.append((str(text), _ref(bill, f"energy.tod.{item_i}.slot", None)))
    kinds: list[str] = []
    for kind, rx in KIND_WORDS:
        hit = next(((t, r) for t, r in texts if rx.search(t)), None)
        if hit and kind not in kinds:
            kinds.append(kind)
            evidence.append(Evidence(finding=f"the bill names {KIND_LABEL[kind]} ('{hit[0]}')", ref=hit[1]))
    if oa_seen or (kinds and kinds != ["exchange"]):
        status: OpenAccess = "open_access"
    elif green:
        status = "green_tariff"
    else:
        status = "none_seen"
    return status, kinds, evidence


def settlement_routes(session: Session, discom: str, on: date) -> list[SettlementRoute]:
    """For each ownership, the approved settlement rule the next stage applies to an intra-state
    solar source commissioned on `on` (nearest jurisdiction first, then most specific)."""
    out = []
    titles: dict[str, tuple[str | None, int | None]] = {}
    for own in OWNERSHIPS:
        ctx = {
            "source": "solar",
            "ownership": own,
            "connection": "intra_state",
            "month": on.month,
            "date": on,
            "commissioned": on,
        }
        try:
            rows = repository.applicable(session, "settlement", discom, ctx, on)
        except UnknownJurisdiction:
            rows = []
        rule = rows[0] if rows else None
        if rule is not None and rule.version_id not in titles:
            v = session.get(RulebookVersion, rule.version_id)
            titles[rule.version_id] = (v.title, v.version) if v else (None, None)
        title, version = titles.get(rule.version_id, (None, None)) if rule else (None, None)
        out.append(
            SettlementRoute(
                ownership=own,
                ownership_label=OWNERSHIP_LABEL[own],
                rule_label=rule.label if rule else None,
                rulebook=title,
                version=version,
                ref=rule.ref() if rule else None,
            )
        )
    return out


def recognise(session: Session, bill: Bill, on: date | None = None) -> Recognition:
    b = _bill_dict(bill)
    found = discom_of(bill)
    discom_name = state = state_name = None
    if found.discom:
        j = session.get(Jurisdiction, found.discom)
        discom_name = j.name if j else None
        state = defaults.state_of(found.discom)
        s = session.get(Jurisdiction, state) if state else None
        state_name = s.name if s else state
    status, kinds, evidence = _open_access(bill, b)
    when = on or bill.bill_month or date.today()
    routes = settlement_routes(session, found.discom, when) if found.discom else []
    notes: list[str] = []
    if not found.discom:
        notes.append("The DISCOM could not be recognised from this bill; say which DISCOM supplies the site.")
    elif routes and not any(r.rule_label for r in routes):
        notes.append(
            f"No approved settlement rules for {state_name or state} yet: banking and set-off are not "
            "applied until the state's regulation is read and approved."
        )
    if status == "open_access" and not kinds:
        notes.append(
            "The bill shows open access but not its kind; "
            "say whether it is captive, group captive or third party."
        )
    return Recognition(
        discom=found.discom,
        discom_name=discom_name,
        discom_how=found.how,
        discom_ref=found.ref,
        state=state,
        state_name=state_name,
        open_access=status,
        open_access_kinds=kinds,
        evidence=evidence,
        settlement=routes,
        notes=notes,
    )
