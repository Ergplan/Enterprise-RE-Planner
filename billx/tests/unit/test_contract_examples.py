"""Every example under contract/examples/<mode>/ runs against the app in that mode and
returns the stored response (timings aside): the Stage 2 bar for both contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from billx.platform.api.app import ApiSettings, create_app
from billx.platform.api.examples import EXAMPLES, MODES, ReplayModel, strip_volatile
from billx.platform.api.render import CONTRACT_1_0_BILL_KEYS, CONTRACT_1_0_FIELD_KEYS

TOKEN = "contract-test-token"


def _cases(mode: str) -> list[Path]:
    folder = EXAMPLES / mode
    return (
        sorted(p for p in folder.iterdir() if (p / "request.json").is_file())
        if folder.is_dir()
        else []
    )


def _replayed(case: Path) -> bool:
    return json.loads((case / "request.json").read_text()).get("models") == "replay"


@pytest.fixture(scope="module", params=MODES)
def mode_client(request, tmp_path_factory):
    """Two apps per mode: one with no model configured, one whose models replay the
    synthetic truth of the examples marked `"models": "replay"`."""
    mode = request.param
    replay_files = [
        case / json.loads((case / "request.json").read_text())["file"]
        for case in _cases(mode)
        if _replayed(case)
    ]
    clients = {}
    for name, providers in (
        ("none", lambda: (None, None)),
        ("replay", lambda: ReplayModel.pair(replay_files)),
    ):
        settings = ApiSettings(
            mode=mode, token=TOKEN, data_dir=tmp_path_factory.mktemp(f"{mode}-{name}"), max_jobs=2
        )
        clients[name] = TestClient(
            create_app(settings, providers=providers),
            headers={"Authorization": f"Bearer {TOKEN}"},
        ).__enter__()
    yield mode, clients
    for c in clients.values():
        c.__exit__(None, None, None)


def _run(client, case: Path) -> dict:
    request = json.loads((case / "request.json").read_text())
    file = case / request["file"]
    r = client.post(
        "/v1/jobs",
        files={"file": (file.name, file.read_bytes(), "application/pdf")},
        data={"options": json.dumps(request["options"])},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    for _ in range(600):
        body = client.get(f"/v1/jobs/{job_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        import time

        time.sleep(0.5)
    raise AssertionError(f"{case.name}: job did not finish")


@pytest.mark.ocr
def test_every_example_matches_its_stored_response(mode_client):
    mode, clients = mode_client
    cases = _cases(mode)
    assert cases, f"no examples for {mode}: run `billx examples --synthetic out/synth`"
    for case in cases:
        expected = json.loads((case / "response.json").read_text())
        body = _run(clients["replay" if _replayed(case) else "none"], case)
        assert body["status"] == "done", (case.name, body.get("error"))
        assert strip_volatile(body["result"]) == strip_volatile(expected), case.name


def test_1_0_examples_carry_only_contract_keys():
    for case in _cases("esgos-1.0"):
        response = json.loads((case / "response.json").read_text())
        if "bills" not in response:
            continue  # a text job
        for bill in response["bills"]:
            assert set(bill) == CONTRACT_1_0_BILL_KEYS, case.name
            stack = [bill["fields"]]
            while stack:
                node = stack.pop()
                if isinstance(node, dict) and "value" in node and "source" in node:
                    assert set(node) == CONTRACT_1_0_FIELD_KEYS, case.name
                elif isinstance(node, dict):
                    stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
                elif isinstance(node, list):
                    stack.extend(v for v in node if isinstance(v, (dict, list)))


def test_the_examples_cover_every_route_and_failure():
    names = {p.name for p in _cases("esgos-1.1")}
    assert {
        "route-cloud-model-passed",
        "printed-inconsistency",
        "digital-without-a-model",
        "model-not-allowed",
        "no-model-configured",
        "not-a-bill",
        "wrong-document-type",
        "gas-bill",
        "kind-text",
    } <= names
    index = json.loads((EXAMPLES / "index.json").read_text())
    assert "Synthetic" in index["note"]
    for case in _cases("esgos-1.1"):
        request = json.loads((case / "request.json").read_text())
        assert "synth" in request["file"], case.name  # synthetic files only, never a real bill
