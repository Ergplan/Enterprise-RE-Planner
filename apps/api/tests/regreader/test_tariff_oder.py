"""Fixtures are shaped exactly as tariff-oder's packages/contracts/openapi.json (TariffExplorer,
NetworkExplorer, PublishedFactOut, CitationOut)."""

from ergplan.regreader.tariff_oder import facts_from_explorer, map_facts
from ergplan.rulebook.schemas import validate_row


def cite(page: int, excerpt: str) -> list[dict]:
    return [
        {
            "evidence_id": "e",
            "source_id": "s1",
            "pdf_page": page,
            "printed_page": str(page),
            "kind": "cell",
            "table_id": "p387-g1",
            "cell": "r3c1",
            "line_no": None,
            "header_path": [],
            "row_path": [],
            "clause_path": [],
            "excerpt": excerpt,
        }
    ]


def fact(
    fid: str,
    family: str,
    comp: str,
    value: str | None,
    unit: str | None,
    app: dict,
    page: int,
    excerpt: str,
    cat: str | None = "HV-2",
    state: str = "value",
    currency: str | None = "rupees",
) -> dict:
    return {
        "fact_id": fid,
        "release_id": "r1",
        "candidate_id": "c" + fid,
        "review_status": "approved",
        "family": family,
        "category_code": cat,
        "component_type": comp,
        "value": value,
        "value_state": state,
        "currency": currency,
        "per_unit": unit,
        "frequency": "per_month" if comp in ("fixed", "demand") else None,
        "decision_status": "approved",
        "period": "FY2026-27",
        "utility": "NPCL",
        "applicability": app,
        "conditions": [],
        "derivation": None,
        "original_text": excerpt,
        "reference_target": None,
        "is_fixture": False,
        "citations": cite(page, excerpt),
    }


TARIFF = {
    "source_id": "s1",
    "status": "published",
    "categories": [
        {
            "category_code": "HV-2",
            "facts": 4,
            "conditions": [],
            "components": {
                "demand": [
                    fact(
                        "1",
                        "retail_tariff",
                        "demand",
                        "300.00",
                        "kVA",
                        {"voltage": "For supply up to 11 kV", "rate_block": "Urban Schedule"},
                        387,
                        "Demand Charges Rs. 300.00 / kVA / month",
                    )
                ],
                "energy": [
                    fact(
                        "2",
                        "retail_tariff",
                        "energy",
                        "7.10",
                        "kVAh",
                        {"voltage": "For supply up to 11 kV", "rate_block": "Urban Schedule"},
                        387,
                        "Energy Charges Rs. 7.10 / kVAh",
                    )
                ],
                "tod_adjustment": [
                    fact(
                        "3",
                        "retail_tariff",
                        "tod_adjustment",
                        "15",
                        "percent",
                        {"time_band": "19:00-02:00", "season": "Summer Months (April to September)"},
                        388,
                        "19:00 hrs – 02:00 hrs (+) 15%",
                    ),
                    fact(
                        "4",
                        "retail_tariff",
                        "tod_adjustment",
                        "-15",
                        "percent",
                        {"time_band": "07:00-16:00", "season": "Summer Months (April to September)"},
                        388,
                        "07:00 hrs – 16:00 hrs (-) 15%",
                    ),
                ],
            },
        }
    ],
    "general_conditions": [],
    "unresolved_items": [],
    "completeness": None,
    "release": None,
    "message": None,
}

NETWORK = {
    "source_id": "s1",
    "status": "published",
    "families": [
        {
            "family": "wheeling_charge",
            "status": "published",
            "disposition": None,
            "message": None,
            "facts": [
                fact(
                    "5",
                    "wheeling_charge",
                    "charge",
                    "0.92",
                    "kWh",
                    {"voltage": "11 kV"},
                    313,
                    "Wheeling charge at 11 kV Rs 0.92/kWh",
                    cat=None,
                ),
                fact(
                    "6",
                    "wheeling_charge",
                    "charge",
                    "45",
                    "kWh",
                    {"voltage": "33 kV"},
                    313,
                    "Wheeling charge at 33 kV 45 paise/kWh",
                    cat=None,
                    currency="paise",
                ),
            ],
        },
        {
            "family": "banking_rule",
            "status": "published",
            "disposition": None,
            "message": None,
            "facts": [
                fact(
                    "7",
                    "banking_rule",
                    "condition",
                    None,
                    None,
                    {},
                    33,
                    "banked power",
                    cat=None,
                    state="cross_reference",
                )
            ],
        },
    ],
}


def test_flatten_and_map() -> None:
    facts = facts_from_explorer(TARIFF, NETWORK)
    assert len(facts) == 7
    m = map_facts(facts, document_id="doc-npcl", effective_from="2026-07-09")
    [sched] = m.by_family["tariff_schedule"]
    assert sched["scope"] == {"category": ["HV-2"], "voltage_kv": {"max": 11}, "rate_block": "Urban Schedule"}
    assert sched["body"]["energy_charge"] == {"base": "7.10"} and sched["body"]["billing_basis"] == "kvah"
    assert sched["body"]["demand_charge"] == {"value": "300.00", "basis": "inr_per_kva_month"}
    assert sched["field_refs"]["/demand_charge/value"]["page"] == 387
    [tod] = m.by_family["tod_slots"]
    assert tod["scope"]["months"] == [4, 5, 6, 7, 8, 9]
    assert tod["body"]["slots"] == [
        {"name": "19:00-02:00", "start": "19:00", "end": "02:00", "surcharge_pct": "15"},
        {"name": "07:00-16:00", "start": "07:00", "end": "16:00", "rebate_pct": "15"},
    ]
    [wheel] = m.by_family["oa_charge"]
    assert wheel["body"]["value_by_voltage"] == {"11": "0.92", "33": "0.45"}
    assert [u.reason for u in m.unmapped] == ["value_state cross_reference"]
    for fam, rows in m.by_family.items():
        for r in rows:
            assert validate_row(fam, {k: v for k, v in r.items() if k != "review"}) == [], (fam, r)
