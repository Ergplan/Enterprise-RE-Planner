#!/usr/bin/env python3
"""A stand-in for billx in end-to-end runs: answers POST /v1/jobs with billx's stored reading of the
same file (data/bills/billx-results/<sha256>.json, written when the real bill was first read), so a
browser journey on real bills costs nothing and needs no network. Unknown files get a 422.

    apps/api/.venv/bin/uvicorn --app-dir tools/dev billx_stub:app --port 8091
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

RESULTS = Path(__file__).resolve().parents[2] / "data" / "bills" / "billx-results"
app = FastAPI(title="billx stub")


@app.get("/v1/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "stub": True, "readings": len(list(RESULTS.glob("*.json")))}


@app.post("/v1/jobs")
async def jobs(file: Annotated[UploadFile, File()], options: Annotated[str, Form()] = "{}") -> JSONResponse:
    sha = hashlib.sha256(await file.read()).hexdigest()
    p = RESULTS / f"{sha}.json"
    if not p.exists():
        return JSONResponse({"error": {"message": f"no stored reading for {sha[:12]}"}}, status_code=422)
    return JSONResponse({"job_id": f"stub-{sha[:12]}", "status": "done", "result": json.loads(p.read_text())["result"]})
