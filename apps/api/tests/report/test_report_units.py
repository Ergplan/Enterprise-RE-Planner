"""Small pieces of report/: what-if wording, Chromium lookup, explanation input (refs only)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ergplan.core.settings import get_settings
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


def test_chromium_is_configured_or_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ergplan_chromium", "/opt/chrome")
    assert pdf.chromium() == "/opt/chrome"
    monkeypatch.setattr(get_settings(), "ergplan_chromium", "")
    monkeypatch.setattr(pdf.shutil, "which", lambda c: None)
    with pytest.raises(pdf.PdfUnavailable):
        pdf.chromium()


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
