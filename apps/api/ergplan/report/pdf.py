"""PDF export of the live plan: headless Chromium (Playwright) prints the same page
(/p/{token}?print=1), whose print layout carries every citation as a numbered note and the
documents as an appendix."""

from __future__ import annotations

from ..core.settings import get_settings


class PdfUnavailable(RuntimeError):
    pass


def page_url(token: str) -> str:
    return f"{get_settings().ergplan_web_internal_url.rstrip('/')}/p/{token}?print=1"


def export(token: str, timeout_s: int = 90) -> bytes:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover - the image installs it
        raise PdfUnavailable("Playwright is not installed") from e
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(page_url(token), wait_until="networkidle", timeout=timeout_s * 1000)
                data = page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
                )
            finally:
                browser.close()
    except PlaywrightError as e:
        raise PdfUnavailable(f"Chromium could not print the plan: {e.message[:300]}") from e
    if len(data) < 1000:
        raise PdfUnavailable("Chromium produced no PDF")
    return data
