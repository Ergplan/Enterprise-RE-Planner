"""Stage 8 end to end in the browser (Playwright): the REopt-style journey. A consumer opens
/evaluate, types the factory, the connection and the year's units (or drops real bills), ticks what
to evaluate and gets results: the full report with the 25-year view, the dispatch, the cost
comparison, every line cited; the shared page and its PDF carry the same sections. Run by
tools/dev/e2e-journey.sh (isolated API, worker, billx stub, Next)."""

from __future__ import annotations

import io
import os
import re

import httpx
import pypdfium2
import pytest

from ergplan.core.settings import REPO_ROOT

from ..engine.helpers import restore_committed

WEB = os.environ.get("E2E_WEB_URL")
API = os.environ.get("E2E_API_URL")
NPCL_BILLS = [
    p
    for p in (
        next((REPO_ROOT / "data" / "bills").rglob("NPCL July - Aug Plant.pdf"), None),
        next((REPO_ROOT / "data" / "bills").rglob("NPCL Bill Plant May-June.pdf"), None),
    )
    if p is not None
]
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not WEB or not API, reason="run through tools/dev/e2e-journey.sh"),
]


def _field(page, label: str):  # type: ignore[no-untyped-def]
    pattern = "^" + re.escape(label) + r"\s*\*?$"
    return page.locator(".ep-fld").filter(has=page.locator("label", has_text=re.compile(pattern))).first


def _wait_for_report(page) -> None:  # type: ignore[no-untyped-def]
    page.wait_for_url(re.compile(r"/results\?c="), timeout=300_000)
    page.wait_for_selector('h2:has-text("25-year view"), .ep-error', timeout=900_000)
    assert page.locator(".ep-error").count() == 0, page.locator(".ep-error").first.text_content()


def _check_shared(page, browser, connection_id: str) -> None:  # type: ignore[no-untyped-def]
    page.click('button:has-text("Create a share link")')
    link = page.locator("a.ep-share-link")
    link.wait_for(timeout=30_000)
    path = link.get_attribute("href")
    assert path and path.startswith("/p/")
    token = path.split("/p/")[1]
    visitor = browser.new_context().new_page()  # logged out
    visitor.goto(f"{WEB}{path}")
    visitor.wait_for_selector("text=Recommended", timeout=60_000)
    for heading in (
        "Cost comparison, year one",
        "25-year view",
        "Dispatch, busiest week",
        "Your year, month by month",
    ):
        assert visitor.locator(f'h2:has-text("{heading}")').count() == 1, heading
    assert visitor.locator("a.ep-ref").count() > 3
    plan = httpx.get(f"{API}/p/{token}", timeout=60).json()
    assert plan["connection_id"] == connection_id and plan["pending_runs"] == 0
    assert plan["scenarios"][0]["summary"]["lifecycle"]["years"][-1]["year"] == 25
    pdf = httpx.get(f"{API}/p/{token}/pdf", timeout=300)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    doc = pypdfium2.PdfDocument(io.BytesIO(pdf.content))
    text = re.sub(r"\s+", " ", " ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))))
    for heading in ("Cost comparison, year one", "25-year view", "Dispatch, busiest week", "Notes"):
        assert heading in text, heading
    assert len(doc) >= 5


def test_typed_site_to_full_report() -> None:
    """No bills: the factory, the connection and the year's units typed; the report in full."""
    from playwright.sync_api import sync_playwright

    restore_committed()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.goto(f"{WEB}/evaluate")
        page.wait_for_selector("text=Your factory")
        page.wait_for_timeout(1500)
        _field(page, "Company").locator("input").fill("Acme Forgings Ltd")
        _field(page, "Site or town").locator("input").fill("Greater Noida unit 2")
        _field(page, "State").locator("select").select_option("UP")
        _field(page, "How the plant runs").locator("select").select_option("two_shift")
        _field(page, "DISCOM").locator("select").select_option("npcl")
        _field(page, "Tariff category").locator("select").select_option("HV-2")
        _field(page, "Supply voltage").locator("input").fill("11")
        _field(page, "Contract demand").locator("input").fill("2500")
        page.click('button:has-text("The year\'s units")')
        _field(page, "Units in the last twelve months").locator("input").fill("9600000")
        _field(page, "Recorded maximum demand").locator("input").fill("2300")
        for label in (
            "Rooftop solar (behind the meter)",
            "Open-access solar, intra-state",
            "Battery behind the meter",
        ):
            t = page.locator(f'button[role=switch][aria-label="{label}"]')
            if t.get_attribute("aria-checked") != "true":
                t.click()
        assert page.locator(".ep-rail__missing").count() == 0
        page.click('.ep-ev__footer button:has-text("Get results")')
        _wait_for_report(page)
        conn = page.url.split("c=")[1].split("&")[0]
        # the report: every section, the lifecycle to year 25, the cost lines cited
        for heading in (
            "Summary",
            "Recommended system",
            "Cost comparison, year one",
            "25-year view",
            "Dispatch",
        ):
            assert page.locator(f'h2:has-text("{heading}")').count() >= 1, heading
        assert page.locator(".ep-cost tbody tr").count() >= 3
        page.click('button:has-text("Show all 25 years")')
        assert page.locator(".ep-lc tbody tr").count() == 26  # year 0 and 25 years
        # the inputs reopen with everything that was typed
        page.goto(f"{WEB}/evaluate?c={conn}")
        page.wait_for_selector("text=Your factory")
        page.wait_for_timeout(2500)
        assert _field(page, "Company").locator("input").input_value() == "Acme Forgings Ltd"
        assert _field(page, "Contract demand").locator("input").input_value().startswith("2500")
        page.goto(f"{WEB}/results?c={conn}")
        page.wait_for_selector('h2:has-text("25-year view")', timeout=60_000)
        _check_shared(page, browser, conn)
        browser.close()


@pytest.mark.skipif(len(NPCL_BILLS) < 2, reason="the real NPCL bills are not present")
def test_bills_to_full_report() -> None:
    """Two real bills dropped: the connection is recognised (category mapped to the order's code),
    the year comes from the bills, and the report follows."""
    from playwright.sync_api import sync_playwright

    restore_committed()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.goto(f"{WEB}/evaluate")
        page.wait_for_selector("text=Your factory")
        page.wait_for_timeout(1200)
        _field(page, "Company").locator("input").fill("Plant Co")
        _field(page, "Site or town").locator("input").fill("Greater Noida")
        page.set_input_files(".ep-drop input[type=file]", [str(p) for p in NPCL_BILLS])
        page.wait_for_selector(".ep-bill", timeout=240_000)
        for _ in range(40):
            btn = page.locator('button:has-text("Looks right")').first
            if btn.count() == 0:
                break
            btn.click()
            page.wait_for_timeout(500)
        page.wait_for_timeout(1500)
        assert _field(page, "DISCOM").locator("select").input_value() == "npcl"
        assert _field(page, "Tariff category").locator("select").input_value() == "HV-2"
        assert _field(page, "Contract demand").locator("input").input_value().startswith("6000")
        if not _field(page, "Supply voltage").locator("input").input_value():
            _field(page, "Supply voltage").locator("input").fill("11")  # not printed on these bills
        page.wait_for_timeout(500)
        assert page.locator(".ep-rail__missing").count() == 0
        page.click('.ep-ev__footer button:has-text("Get results")')
        _wait_for_report(page)
        assert page.locator('h2:has-text("25-year view")').count() == 1
        assert page.locator('.eg-chip:has-text("bill")').count() > 0  # figures cite the bill
        browser.close()
