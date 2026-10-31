"""A fake billx speaking contract 1.1 over httpx's MockTransport, answering with the contract
examples in tests/fixtures/billx (synthetic bills)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx

from ergplan.intake.billx_client import BillxClient

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "billx"


def result(name: str) -> dict[str, Any]:
    return dict(json.loads((FIX / f"{name}.json").read_text()))


def pdf(tag: str = "") -> bytes:
    """The synthetic PVVNL bill, made distinct per tag so each counts as a new file."""
    return (FIX / "pvvnl_synth.pdf").read_bytes() + (f"\n%tag-{tag}\n".encode() if tag else b"")


def with_month(res: dict[str, Any], month: str, kwh: str | None = None) -> dict[str, Any]:
    r = copy.deepcopy(res)
    f = r["bills"][0]["fields"]
    f["period"]["bill_month"]["value"] = month
    if kwh:
        f["energy"]["kwh"]["value"] = kwh
    return r


class FakeBillx:
    """Answers POST /v1/jobs with the result registered for the uploaded file's tag."""

    def __init__(self) -> None:
        self.by_tag: dict[str, dict[str, Any]] = {}
        self.calls = 0
        self.down = False
        self.options: list[dict[str, Any]] = []

    def register(self, tag: str, res: dict[str, Any]) -> bytes:
        self.by_tag[tag] = res
        return pdf(tag)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        self.calls += 1
        if request.method == "POST" and request.url.path == "/v1/jobs":
            body = request.content
            marker = body.find(b"%tag-")
            tag = body[marker + 5 : body.find(b"\n", marker)].decode() if marker >= 0 else ""
            opts = body.find(b'name="options"')
            if opts >= 0:
                start = body.find(b"{", opts)
                self.options.append(json.loads(body[start : body.find(b"\r\n", start)]))
            res = self.by_tag.get(tag) or result("pvvnl_passed")
            return httpx.Response(200, json={"job_id": f"job-{tag or 'x'}", "status": "done", "result": res})
        return httpx.Response(404, json={"error": {"message": "no"}})

    def client(self) -> BillxClient:
        return BillxClient(
            base_url="http://billx.test", token="t", transport=httpx.MockTransport(self.handler)
        )
