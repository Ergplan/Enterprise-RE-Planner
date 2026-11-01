"""billx over HTTP (invariant 7: billx is the only bill reader; ergPLAN never reads a bill itself).
Contract esgos-1.1: POST /v1/jobs (multipart file + options), GET /v1/jobs/{id}."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..core.settings import get_settings


class BillxError(RuntimeError):
    pass


class BillxUnavailable(BillxError):
    pass


@dataclass(frozen=True)
class BillxJob:
    job_id: str
    status: str  # queued|reading|done|failed
    result: dict[str, Any] | None
    error: dict[str, Any] | None


class BillxClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        st = get_settings()
        self.http = httpx.Client(
            base_url=(base_url or st.billx_url).rstrip("/"),
            headers={"Authorization": f"Bearer {token if token is not None else st.billx_token}"},
            timeout=httpx.Timeout(180.0, connect=5.0),
            transport=transport,
        )

    def health(self) -> dict[str, Any]:
        try:
            return dict(self.http.get("/v1/health").raise_for_status().json())
        except httpx.HTTPError as e:
            raise BillxUnavailable(f"billx is not reachable: {type(e).__name__}") from e

    def submit(
        self,
        data: bytes,
        filename: str,
        account_ref: str | None = None,
        allow_cloud_model: bool = True,
        max_cost_usd: str | None = None,
        wait: bool = True,
    ) -> BillxJob:
        options: dict[str, Any] = {
            "request_id": "ergplan-" + hashlib.sha256(data).hexdigest()[:24] + f"-{int(time.time())}",
            "product": "ergplan",
            "kind": "bill",
            "allow_cloud_model": allow_cloud_model,
            "max_cost_usd": max_cost_usd or get_settings().billx_max_cost_usd,
            "wait": wait,
        }
        if account_ref:
            options["account_ref"] = account_ref[:64]
        try:
            r = self.http.post(
                "/v1/jobs",
                files={"file": (filename, data, "application/pdf")},
                data={"options": json.dumps(options)},
            )
        except httpx.HTTPError as e:
            raise BillxUnavailable(f"billx is not reachable: {type(e).__name__}") from e
        body = r.json()
        if r.status_code >= 400:
            raise BillxError(f"billx refused the bill: {body.get('error', {}).get('message', r.status_code)}")
        return BillxJob(body["job_id"], body.get("status", "queued"), body.get("result"), body.get("error"))

    def job(self, job_id: str) -> BillxJob:
        try:
            body = self.http.get(f"/v1/jobs/{job_id}").raise_for_status().json()
        except httpx.HTTPError as e:
            raise BillxUnavailable(f"billx is not reachable: {type(e).__name__}") from e
        return BillxJob(body["job_id"], body["status"], body.get("result"), body.get("error"))

    def read(
        self,
        data: bytes,
        filename: str,
        account_ref: str | None = None,
        timeout_s: float | None = None,
        poll_s: float = 3,
    ) -> dict[str, Any]:
        """Submit and wait for the finished result (polling past billx's 50-second wait)."""
        job = self.submit(data, filename, account_ref=account_ref)
        timeout_s = timeout_s or float(get_settings().billx_timeout_s)
        deadline = time.monotonic() + timeout_s
        while job.status not in ("done", "failed"):
            if time.monotonic() > deadline:
                raise BillxError(f"billx job {job.job_id} did not finish in {timeout_s:.0f} s")
            time.sleep(poll_s)
            job = self.job(job.job_id)
        if job.status == "failed" or job.result is None:
            raise BillxError(f"billx could not read the file: {(job.error or {}).get('message', 'failed')}")
        return job.result
