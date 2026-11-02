"""contract/openapi.json is generated from the app and checked in: the five contract calls
and /metrics, nothing else."""

import json
from pathlib import Path

from billx.platform.api.openapi import openapi_document, write_openapi

ROOT = Path(__file__).resolve().parents[2]


def test_the_document_lists_exactly_the_contract_calls():
    doc = openapi_document()
    assert set(doc["paths"]) == {
        "/v1/health",
        "/v1/jobs",
        "/v1/jobs/{job_id}",
        "/v1/feedback",
        "/metrics",
    }
    assert set(doc["paths"]["/v1/jobs"]) == {"post"}
    assert set(doc["paths"]["/v1/jobs/{job_id}"]) == {"get", "delete"}


def test_the_checked_in_file_is_current():
    out = ROOT / "contract" / "openapi.json"
    assert out.is_file(), "run `billx openapi`"
    assert not write_openapi(out, check=True), "contract/openapi.json is stale: run `billx openapi`"
    assert "info" in json.loads(out.read_text())
