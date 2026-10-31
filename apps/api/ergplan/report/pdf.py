"""PDF export of the live plan: headless Chromium prints the same page (/p/{token}?print=1), whose
print layout carries every citation as a footnote and the documents as an appendix."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..core.settings import get_settings

CANDIDATES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


class PdfUnavailable(RuntimeError):
    pass


def chromium() -> str:
    configured = get_settings().ergplan_chromium
    if configured:
        return configured
    for c in CANDIDATES:
        p = shutil.which(c)
        if p:
            return p
    raise PdfUnavailable("no Chromium found; set ERGPLAN_CHROMIUM")


def page_url(token: str) -> str:
    return f"{get_settings().ergplan_web_internal_url.rstrip('/')}/p/{token}?print=1"


def export(token: str, timeout_s: int = 90) -> bytes:
    with tempfile.TemporaryDirectory(prefix="ergplan-pdf-") as d:
        out = Path(d) / "plan.pdf"
        cmd = [
            chromium(),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--virtual-time-budget=20000",
            f"--user-data-dir={d}/profile",
            f"--print-to-pdf={out}",
            page_url(token),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise PdfUnavailable(f"Chromium could not print the plan: {e}") from e
        if not out.exists() or out.stat().st_size < 1000:
            raise PdfUnavailable("Chromium produced no PDF")
        return out.read_bytes()
