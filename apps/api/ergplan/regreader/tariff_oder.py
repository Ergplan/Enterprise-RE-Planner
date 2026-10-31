"""Import published facts from Ergplan/tariff-oder (the upstream tariff-order pipeline) as draft
rule rows. tariff-oder's facts are already human-reviewed there; ergPLAN maps them into its own
families and an analyst approves the mapped rulebook here. Each fact's first citation (PDF page,
printed page, excerpt) becomes that field's source_ref. Facts that do not map are listed with the
reason, never dropped silently.

Inputs: the API (`/explorer/sources/{id}/tariff`, `/network`, `/sources/{id}`) or the
`export.zip` / exchange folder. Contract: tariff-oder packages/contracts/openapi.json.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from ..core.units import Unit, convert
from .voltage import band_key, parse_band

NETWORK_COMPONENT = {
    "wheeling_charge": "wheeling",
    "cross_subsidy_surcharge": "cross_subsidy_surcharge",
    "additional_surcharge": "additional_surcharge",
    "green_tariff": "green_tariff_premium",
    "transmission_reference": "stu_transmission",
}
MAPPABLE_STATES = {"value", "zero"}
MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}


@dataclass
class Unmapped:
    fact_id: str
    family: str
    reason: str


@dataclass
class Mapped:
    by_family: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    unmapped: list[Unmapped] = field(default_factory=list)
    facts_read: int = 0


class TariffOderClient:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=60,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )

    def source(self, source_id: str) -> dict[str, Any]:
        return dict(self.http.get(f"/sources/{source_id}").raise_for_status().json())

    def tariff(self, source_id: str) -> dict[str, Any]:
        return dict(self.http.get(f"/explorer/sources/{source_id}/tariff").raise_for_status().json())

    def network(self, source_id: str) -> dict[str, Any]:
        return dict(self.http.get(f"/explorer/sources/{source_id}/network").raise_for_status().json())


def facts_from_explorer(
    tariff: dict[str, Any] | None, network: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Flatten the two explorer views into a list of PublishedFactOut dicts."""
    facts: list[dict[str, Any]] = []
    for cat in (tariff or {}).get("categories", []):
        for comp in (cat.get("components") or {}).values():
            facts += comp if isinstance(comp, list) else [comp]
    for fam in (network or {}).get("families", []):
        facts += fam.get("facts", [])
    return [f for f in facts if isinstance(f, dict) and not f.get("is_fixture")]


def _ref(fact: dict[str, Any], document_id: str, effective_from: str | None) -> dict[str, Any]:
    c = (fact.get("citations") or [{}])[0]
    excerpt = (c.get("excerpt") or fact.get("original_text") or "").strip()
    ref: dict[str, Any] = {
        "kind": "order",
        "document_id": document_id,
        "page": int(c.get("pdf_page") or 0),
        "quote": excerpt[:400],
        "note": f"tariff-oder fact {fact.get('fact_id')} (release {fact.get('release_id')})",
    }
    if c.get("printed_page"):
        ref["printed_page"] = str(c["printed_page"])
    if effective_from:
        ref["effective_from"] = effective_from
    return ref


def _inr(fact: dict[str, Any]) -> str:
    """Rupee values as printed; paise converted to rupees (the only arithmetic, a unit change)."""
    if (fact.get("currency") or "rupees") != "paise":
        return str(fact["value"])
    return format(convert(Decimal(str(fact["value"])), Unit.PAISE_PER_KWH, Unit.INR_PER_KWH), "f")


def _months(season: str | None) -> list[int] | None:
    if not season:
        return None
    found = [
        MONTHS[m]
        for m in re.findall(
            r"(january|february|march|april|may|june|july|august|september|october|november|december)",
            season.lower(),
        )
    ]
    if len(found) < 2:
        return None
    a, b = found[0], found[-1]
    return list(range(a, b + 1)) if a <= b else list(range(a, 13)) + list(range(1, b + 1))


def _band(time_band: str) -> tuple[str, str] | None:
    m = re.findall(r"(\d{1,2})[:.](\d{2})", time_band)
    if len(m) < 2:
        return None
    return f"{int(m[0][0]):02d}:{m[0][1]}", f"{int(m[1][0]):02d}:{m[1][1]}"


def map_facts(facts: list[dict[str, Any]], document_id: str, effective_from: str | None = None) -> Mapped:
    out = Mapped(facts_read=len(facts))
    schedule: dict[tuple[str, str, str], dict[str, Any]] = {}
    tod: dict[tuple[str, str], dict[str, Any]] = {}
    oa: dict[tuple[str, str, str], dict[str, Any]] = {}
    for f in facts:
        fid, fam = str(f.get("fact_id")), str(f.get("family"))
        if f.get("value_state") not in MAPPABLE_STATES or f.get("value") is None:
            out.unmapped.append(Unmapped(fid, fam, f"value_state {f.get('value_state')}"))
            continue
        if not f.get("citations"):
            out.unmapped.append(Unmapped(fid, fam, "no citation"))
            continue
        app = f.get("applicability") or {}
        ref = _ref(f, document_id, effective_from)
        cat = f.get("category_code")
        comp = f.get("component_type")
        if fam == "retail_tariff" and comp in ("energy", "fixed", "demand") and cat:
            vband = parse_band(app.get("voltage"))
            skey = (cat, str(app.get("voltage") or ""), str(app.get("rate_block") or ""))
            row = schedule.setdefault(
                skey,
                {
                    "label": " · ".join(x for x in (cat, app.get("rate_block"), app.get("voltage")) if x),
                    "scope": {
                        "category": [cat],
                        **({"voltage_kv": vband} if vband else {}),
                        **({"rate_block": app["rate_block"]} if app.get("rate_block") else {}),
                    },
                    "body": {"category": cat},
                    "source_ref": ref,
                    "field_refs": {},
                },
            )
            unit = (f.get("per_unit") or "").lower()
            if comp == "energy":
                row["body"]["energy_charge"] = {"base": _inr(f)}
                row["body"]["billing_basis"] = "kvah" if "kvah" in unit else "kwh"
                row["field_refs"]["/energy_charge/base"] = ref
                row["source_ref"] = ref
            else:
                basis = "inr_per_kw_month" if unit == "kw" else "inr_per_kva_month"
                row["body"]["demand_charge"] = {"value": _inr(f), "basis": basis}
                row["field_refs"]["/demand_charge/value"] = ref
        elif fam == "retail_tariff" and comp == "tod_adjustment" and cat and app.get("time_band"):
            se = _band(str(app["time_band"]))
            if not se:
                out.unmapped.append(Unmapped(fid, fam, f"time band not read: {app['time_band']}"))
                continue
            months = _months(app.get("season"))
            tkey = (cat, str(app.get("season") or ""))
            row = tod.setdefault(
                tkey,
                {
                    "label": f"{cat} · ToD" + (f" · {app['season']}" if app.get("season") else ""),
                    "scope": {"category": [cat], **({"months": months} if months else {})},
                    "body": {"slots": []},
                    "source_ref": ref,
                },
            )
            slot: dict[str, Any] = {"name": str(app["time_band"]), "start": se[0], "end": se[1]}
            pct = format(abs(Decimal(str(f["value"]))), "f")
            sign = f.get("sign") or (1 if not str(f["value"]).startswith("-") else -1)
            if Decimal(pct) != 0:
                slot["surcharge_pct" if sign > 0 else "rebate_pct"] = pct
            row["body"]["slots"].append(slot)
        elif fam in NETWORK_COMPONENT or fam == "oa_loss":
            component = NETWORK_COMPONENT.get(fam) or "wheeling_losses"
            unit = (f.get("per_unit") or "").lower()
            basis = (
                "percent_in_kind"
                if fam == "oa_loss" or unit == "percent"
                else "inr_per_mw_month"
                if "mw" in unit
                else "inr_per_kwh"
            )
            vkey = band_key(parse_band(app.get("voltage")))
            okey = (component, cat or "", basis)
            row = oa.setdefault(
                okey,
                {
                    "label": " · ".join(x for x in (component.replace("_", " "), cat) if x),
                    "scope": {"connection": ["intra_state"], **({"category": [cat]} if cat else {})},
                    "body": {"component": component, "basis": basis},
                    "source_ref": ref,
                    "field_refs": {},
                },
            )
            value = _inr(f) if basis != "percent_in_kind" else format(Decimal(str(f["value"])), "f")
            if vkey:
                row["body"].setdefault("value_by_voltage", {})[vkey] = value
                row["field_refs"][f"/value_by_voltage/{vkey}"] = ref
            else:
                row["body"]["value"] = value
        else:
            out.unmapped.append(Unmapped(fid, fam, f"no ergPLAN family for {fam}/{comp}"))
    for row in schedule.values():
        if "energy_charge" not in row["body"] or "demand_charge" not in row["body"]:
            out.unmapped.append(
                Unmapped(row["label"], "retail_tariff", "row lacks an energy or a demand charge")
            )
            continue
        out.by_family["tariff_schedule"].append(_tidy(row))
    out.by_family["tod_slots"] += [_tidy(r) for r in tod.values()]
    out.by_family["oa_charge"] += [_tidy(r) for r in oa.values()]
    return out


def _tidy(row: dict[str, Any]) -> dict[str, Any]:
    if not row.get("field_refs"):
        row.pop("field_refs", None)
    row["review"] = {"reader": "tariff_oder", "decision": "proposed"}
    return row
