"""Small pieces of report/: what-if wording, Chromium lookup, explanation input (refs only)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ergplan.report import pdf
from ergplan.report.explain import _lines
from ergplan.report.whatif import WhatIf


def test_what_if_describes_itself_in_words() -> None:
    w = WhatIf(
        prices={"oa_solar_intra": Decimal("3.4")},
        capacities_mw={"btm_bess": Decimal("1")},
        contract_demand_kva=Decimal("4500"),
        off=["rooftop_pv"],
        as_of=date(2026, 9, 1),
    )
    assert w.describe() == (
        "open-access solar, intra-state at ₹3.4/kWh, battery behind the meter at 1 MW, contract demand 4500 kVA, "
        "no rooftop solar (behind the meter), the rules in force on 01 Sep 2026"
    )
    assert WhatIf().describe() == "no change"


def test_the_pdf_prints_the_plan_page_in_print_mode() -> None:
    assert pdf.page_url("abc").endswith("/p/abc?print=1")


def test_explanation_input_keeps_values_and_sources_only() -> None:
    v = {
        "label": "CSS",
        "value": "1.25",
        "unit": "INR/kWh",
        "source_refs": [
            {
                "kind": "order",
                "document_id": "d1",
                "page": 106,
                "quote": "x" * 500,
                "url": "/documents/d1#page=106",
            }
        ],
    }
    [line] = _lines([v], {"d1": "MERC MYT order"})
    assert line == {
        "label": "CSS",
        "value": "1.25",
        "unit": "INR/kWh",
        "sources": [{"kind": "order", "document": "MERC MYT order", "page": 106, "quote": "x" * 240}],
    }
