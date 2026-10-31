"""Stage 7 end to end in the browser (Playwright), on two real bills: a new client drops a bill,
confirms what billx could not verify, saves the site, builds the plan and shares it — no analyst
anywhere. A logged-out visitor opens /p/{token}; the PDF carries every citation; the jouleWise view
is refused to the client. Run by tools/dev/e2e-journey.sh (isolated API, worker, billx stub, Next)."""

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
BILLS = {
    "npcl": next((REPO_ROOT / "data" / "bills").rglob("NPCL July - Aug Plant.pdf"), None),
    "msedcl": next((REPO_ROOT / "data" / "bills").rglob("bill_500_251019006990_202604.pdf"), None),
}
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not WEB or not API, reason="run through tools/dev/e2e-journey.sh"),
]


@pytest.mark.parametrize("which", sorted(BILLS))
def test_bill_drop_to_shared_plan_without_an_analyst(which: str) -> None:
    from playwright.sync_api import sync_playwright

    bill = BILLS[which]
    if bill is None:
        pytest.skip(f"the real {which} bill is not present")
    restore_committed()  # the suite's cleanup empties the database after each test
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{WEB}/plan/intake")
        page.set_input_files("input[type=file]", str(bill))
        page.wait_for_selector(".ep-bill", timeout=180_000)
        for _ in range(30):
            btn = page.locator('button:has-text("Looks right")').first
            if btn.count() == 0:
                break
            btn.click()
            page.wait_for_timeout(600)
        page.click('button:has-text("Continue with")')
        page.wait_for_selector("text=What we understood", timeout=60_000)
        page.click('button:has-text("Save and build")')
        page.wait_for_url(re.compile(r"plan/site\?c="), timeout=120_000)
        conn = page.url.split("c=")[1].split("&")[0]
        # step 6 from the rail: the rail carries the site
        page.click('a.ep-step:has-text("Your plan")')
        page.wait_for_url(re.compile(r"plan/report\?c="))
        page.click('button:has-text("Build my plan")')
        page.wait_for_selector("text=Share my plan", timeout=900_000)
        page.wait_for_function("!document.querySelector('.ep-plan-status')", timeout=900_000)
        page.click('button:has-text("Share my plan")')
        link = page.locator("a.ep-share-link")
        link.wait_for(timeout=30_000)
        path = link.get_attribute("href")
        assert path and path.startswith("/p/")
        token = path.split("/p/")[1]

        visitor = browser.new_context().new_page()  # logged out: a fresh context, no storage
        visitor.goto(f"{WEB}{path}")
        visitor.wait_for_selector("text=Recommended", timeout=60_000)
        assert visitor.locator("a.ep-ref").count() > 3  # page chips that open the orders
        assert visitor.locator("text=Documents this plan cites").count() == 1
        browser.close()

    plan = httpx.get(f"{API}/p/{token}", timeout=60).json()
    assert len(plan["scenarios"]) == 3 and plan["pending_runs"] == 0 and plan["connection_id"] == conn
    assert httpx.get(f"{API}/p/{token}", params={"view": "analyst"}, timeout=60).status_code == 403
    pdf = httpx.get(f"{API}/p/{token}/pdf", timeout=180)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    doc = pypdfium2.PdfDocument(io.BytesIO(pdf.content))
    text = " ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    text = re.sub(r"\s+", " ", text)
    assert re.search(r"Notes .*page \d+", text)  # citations as numbered notes
    for d in plan["documents"]:  # every cited document and page is in the appendix
        assert f"{d['title'][:40]}" in text and "pages " + ", ".join(str(p) for p in d["pages"]) in text, d
