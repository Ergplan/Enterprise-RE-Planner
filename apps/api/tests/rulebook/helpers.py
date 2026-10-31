from datetime import date
from typing import Any

REF = {
    "kind": "order",
    "document_id": "doc-npcl",
    "page": 384,
    "quote": "For supply at 11kV Rs. 430.00 / kVA / month Rs. 8.32 / kVAh",
}


def schedule_row(
    category: str, vmin: float | None, vmax: float | None, energy: str, demand: str, **kw: Any
) -> dict[str, Any]:
    band: dict[str, Any] = {}
    if vmin is not None:
        band["min"] = vmin
    if vmax is not None:
        band["max"] = vmax
    band.update(kw.pop("band", {}))
    return {
        "label": f"{category} · {vmin}-{vmax} kV",
        "scope": {"category": [category], "voltage_kv": band},
        "body": {
            "category": category,
            "billing_basis": "kvah",
            "demand_charge": {"value": demand, "basis": "inr_per_kva_month"},
            "energy_charge": {"base": energy},
        },
        "source_ref": REF,
        **kw,
    }


GOLDEN = [
    {
        "name": "11 kV energy",
        "given": {"context": {"category": "HV-2", "voltage_kv": 11}, "field": "/energy_charge/base"},
        "expect": {"value": "8.32"},
    },
    {
        "name": "33 kV demand",
        "given": {"context": {"category": "HV 2", "voltage_kv": 33}, "field": "/demand_charge/value"},
        "expect": {"value": "400"},
    },
    {
        "name": "no LT row",
        "given": {"context": {"category": "HV-2", "voltage_kv": 0.4}},
        "expect": {"absent": True},
    },
]

ROWS = [
    schedule_row("HV-2", 11, 11, "8.32", "430.00"),
    schedule_row("HV-2", 11, None, "8.12", "400.00", band={"min_exclusive": True}),
]

EFFECTIVE = date(2026, 7, 9)
