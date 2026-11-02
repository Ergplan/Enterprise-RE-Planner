"""Studio confirmation mode end to end, on synthetic bills only."""

import io
import json
import logging
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from reportlab.pdfgen import canvas

from billx.core.schema import BillResult, CheckResult, Envelope, FileInfo, Reading, make_value
from billx.platform.studio import golden
from billx.platform.studio.app import NOT_PRINTED, create_app, load_fields
from billx.platform.studio.workspace import Workspace, resolve_workspace

PREFILL = {
    "utility.name": "SYNTHETIC POWER DISCOM",
    "consumer.account_number": "SYN-0012-3456",
    "energy.kwh": "1,234.50",
    "totals.net_payable": "9,876.00",
}


def _reading(reader, raw, ft):
    from billx.core.normalize import normalise

    method = {"text_layer": "text_layer", "local_ocr": "ocr", "model_a": "vision"}[reader]
    fam = "openai" if reader == "model_a" else None
    return Reading(
        reader=reader, method=method, family=fam, raw=raw, normalised=normalise(raw, ft), page=0
    )


def fake_envelope(values: dict[str, str]) -> Envelope:
    """An engine result whose fields were read by the text layer and Model A (so verified),
    except totals.net_payable, where Model A disagrees (disputed)."""
    _, fields = load_fields("electricity")
    types = {f["path"]: f["type"] for f in fields}
    out = []
    for path, raw in values.items():
        other = raw.replace("9,876", "9,376") if path == "totals.net_payable" else raw
        readings = (
            _reading("text_layer", raw, types[path]),
            _reading("model_a", other, types[path]),
        )
        out.append(make_value(path, types[path], readings))
    bill = BillResult(
        index=0,
        pages=(1,),
        bill_type="electricity",
        document_type="electricity_bill",
        route="template",
        fields=tuple(out),
        passed=False,
        status="needs_review",
        review_reasons=("disputed:totals.net_payable",),
        accepted=False,
        checks=(
            CheckResult(id="G09", description="net payable adds up", status="warn", detects="x"),
        ),
    )
    return Envelope(
        contract_version="1.1",
        file=FileInfo(sha256="0" * 64, pages=1, media_type="application/pdf"),
        bills=(bill,),
        seconds=Decimal("0.1"),
    )


class FakeReader:
    def __init__(self):
        self.calls = []

    def __call__(self, path, allow_cloud):
        self.calls.append((path.name, allow_cloud))
        return fake_envelope(PREFILL)


@pytest.fixture
def source(tmp_path):
    src = tmp_path / "synthetic-bills"
    src.mkdir()
    c = canvas.Canvas(str(src / "synthetic.pdf"))
    c.drawString(72, 750, "SYNTHETIC POWER DISCOM - test bill, not real")
    c.drawString(72, 730, "Units consumed (kWh): 1,234.50")
    c.drawString(72, 710, "Net payable: 9,876.00")
    c.save()
    Image.new("RGB", (60, 80), "white").save(src / "photo.png")
    return src


def _client(tmp_path, reader, allow_cloud=True):
    ws = Workspace(resolve_workspace("test"))
    client = TestClient(create_app(ws, reader=reader))
    data = {"confirmer": "Test Person"}
    if allow_cloud:
        data["allow_cloud"] = "1"
    assert client.post("/session", data=data).status_code == 200
    return ws, client


def _sha_of(ws, name):
    return next(sha for sha, b in ws.bills.items() if b["name"] == name)


def _form(values: dict[str, str | None], kind="electricity", opened_at_ms=None):
    """values: path -> value to confirm, or None for not printed."""
    _, fields = load_fields(kind)
    form = {
        "kind": kind,
        "discom": "SYNTH",
        "layout_id": "synth-lt-2026",
        "input_kind": "digital_pdf",
        "opened_at_ms": str(opened_at_ms or time.time_ns() // 1_000_000),
    }
    for i, f in enumerate(fields):
        value = values.get(f["path"])
        if value is None:
            form[f"np_{i}"] = "1"
        else:
            form[f"v_{i}"] = value
            form[f"c_{i}"] = "1"
    return form


def _no_floats(obj):
    if isinstance(obj, dict):
        return all(_no_floats(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_floats(v) for v in obj)
    return not isinstance(obj, float)


def test_workspace_lives_under_the_data_dir(tmp_path):
    assert resolve_workspace("test") == tmp_path / "billx-data" / "workspaces" / "test"
    assert golden.manifest_path() == tmp_path / "billx-data" / "golden" / "manifest.jsonl"


def test_bill_is_prefilled_confirmed_and_written_to_the_manifest(tmp_path, source, caplog):
    caplog.set_level(logging.DEBUG)
    fake = FakeReader()
    ws, client = _client(tmp_path, fake)
    r = client.post("/sources", data={"folder": str(source)})
    assert r.status_code == 200 and "2 new bill(s) added" in r.text
    sha = _sha_of(ws, "synthetic.pdf")
    assert ws.bills[sha]["input_kind"] == "digital_pdf"
    assert ws.bills[sha]["path"] == str((source / "synthetic.pdf").resolve())

    page = client.get(f"/bills/{sha}")
    assert page.status_code == 200
    assert "1,234.50" in page.text and f"/bills/{sha}/pages/0" in page.text
    assert fake.calls == [("synthetic.pdf", True)]
    assert "verified" in page.text and "disputed" in page.text and "G09" in page.text
    img = client.get(f"/bills/{sha}/pages/0")
    assert img.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(img.content)).size[0] > 0

    _, fields = load_fields("electricity")
    values = dict(PREFILL)
    values["totals.net_payable"] = "9,867.00"  # the person corrects a misread
    values["energy.kvah"] = "1,300.0"  # typed: the model gave nothing
    opened = time.time_ns() // 1_000_000 - 7000
    r = client.post(
        f"/bills/{sha}", data=_form(values, opened_at_ms=opened), follow_redirects=False
    )
    assert r.status_code == 303
    png_sha = _sha_of(ws, "photo.png")
    assert r.headers["location"] == f"/bills/{png_sha}"  # the next unconfirmed bill

    lines = golden.manifest_path().read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["sha256"] == sha
    assert entry["source_path"] == str((source / "synthetic.pdf").resolve())
    assert entry["discom"] == "SYNTH" and entry["layout_id"] == "synth-lt-2026"
    assert entry["input_kind"] == "digital_pdf" and entry["bill_kind"] == "electricity"
    assert entry["confirmed_by"] == "Test Person"
    assert entry["split"] == "tuning"
    assert entry["seconds"] in (7, 8)
    assert entry["prefill_model"] == "model_a,text_layer"
    assert entry["supersedes"] is None
    assert set(entry["fields"]) == {f["path"] for f in fields}
    assert all(isinstance(v, str) for v in entry["fields"].values())
    assert entry["fields"]["energy.kwh"] == "1,234.50"
    assert entry["fields"]["totals.net_payable"] == "9,867.00"
    assert entry["fields"]["energy.kvah"] == "1,300.0"
    assert entry["fields"]["consumer.name"] == NOT_PRINTED
    matched = set(entry["matched_prefill"])
    assert {"utility.name", "consumer.account_number", "energy.kwh", "consumer.name"} <= matched
    assert "totals.net_payable" not in matched and "energy.kvah" not in matched
    assert _no_floats(entry)

    # reopening uses the cached pre-fill: no second model call
    assert "Already confirmed by Test Person" in client.get(f"/bills/{sha}").text
    assert len(fake.calls) == 1

    # a correction appends and supersedes; the first entry stays readable
    values["totals.net_payable"] = "9,876.00"
    client.post(f"/bills/{sha}", data=_form(values))
    entries = golden.read_entries()
    assert len(entries) == 2
    latest = golden.latest_by_sha()[sha]
    assert latest["fields"]["totals.net_payable"] == "9,876.00"
    assert latest["supersedes"] == entries[0]["confirmed_at"]

    # privacy: no bill value reaches the logs
    for value in ("1,234.50", "9,867.00", "SYN-0012-3456", "SYNTHETIC POWER DISCOM"):
        assert value not in caplog.text


def test_image_bill_is_shown_as_it_is(tmp_path, source):
    ws, client = _client(tmp_path, FakeReader())
    client.post("/sources", data={"folder": str(source)})
    sha = _sha_of(ws, "photo.png")
    assert ws.bills[sha]["input_kind"] == "scan"
    img = client.get(f"/bills/{sha}/pages/0")
    assert img.headers["content-type"] == "image/png"
    assert img.content == (source / "photo.png").read_bytes()


def test_unconfirmed_field_is_refused_and_nothing_is_written(tmp_path, source):
    ws, client = _client(tmp_path, FakeReader())
    client.post("/sources", data={"folder": str(source)})
    sha = _sha_of(ws, "synthetic.pdf")
    client.get(f"/bills/{sha}")
    form = _form(dict(PREFILL))
    form.pop("c_0")  # utility: neither confirmed nor marked not printed
    r = client.post(f"/bills/{sha}", data=form)
    assert r.status_code == 400
    assert "Not saved" in r.text and "<code>utility.name</code>" in r.text
    assert not golden.manifest_path().exists()


def test_an_engine_failure_leaves_the_studio_usable(tmp_path, source):
    """When the engine cannot read a bill, the person types the values; nothing is pre-filled
    and nothing is recorded as matched."""

    def broken(path, allow_cloud):
        raise RuntimeError("engine not available in this test")

    ws, client = _client(tmp_path, broken)
    client.post("/sources", data={"folder": str(source)})
    sha = _sha_of(ws, "synthetic.pdf")
    page = client.get(f"/bills/{sha}")
    assert page.status_code == 200
    assert "could not read this bill" in page.text
    assert "1,234.50" not in page.text

    values = dict(PREFILL)
    r = client.post(f"/bills/{sha}", data=_form(values), follow_redirects=False)
    assert r.status_code == 303
    entry = golden.latest_by_sha()[sha]
    assert entry["prefill_model"] is None and entry["matched_prefill"] == []
    assert entry["fields"]["energy.kwh"] == "1,234.50"


def test_no_key_means_local_readers_only(tmp_path, source):
    ws = Workspace(resolve_workspace("test"))
    client = TestClient(create_app(ws, reader=FakeReader()))
    client.post("/session", data={"confirmer": "Test Person", "allow_cloud": "1"})
    page = client.get("/")
    assert "no model key is configured: local readers only" in page.text


def test_unticked_cloud_model_is_passed_to_the_reader(tmp_path, source):
    fake = FakeReader()
    ws, client = _client(tmp_path, fake, allow_cloud=False)
    client.post("/sources", data={"folder": str(source)})
    client.get(f"/bills/{_sha_of(ws, 'synthetic.pdf')}")
    assert fake.calls == [("synthetic.pdf", False)]
    assert "local readers only" in client.get("/").text


def test_changed_file_is_not_shown(tmp_path, source):
    ws, client = _client(tmp_path, FakeReader())
    client.post("/sources", data={"folder": str(source)})
    sha = _sha_of(ws, "photo.png")
    Image.new("RGB", (61, 80), "white").save(source / "photo.png")
    assert client.get(f"/bills/{sha}").status_code == 410


def test_a_stale_prefill_is_read_again_and_the_reread_link_forces_it(tmp_path, source, monkeypatch):
    from billx.platform.studio import app as studio_app

    fake = FakeReader()
    ws, client = _client(tmp_path, fake)
    client.post("/sources", data={"folder": str(source)})
    sha = _sha_of(ws, "synthetic.pdf")
    client.get(f"/bills/{sha}")
    client.get(f"/bills/{sha}")
    assert len(fake.calls) == 1  # cached while nothing changed
    monkeypatch.setattr(studio_app, "engine_fingerprint", lambda allow: "changed")
    client.get(f"/bills/{sha}")
    assert len(fake.calls) == 2  # the engine or a key changed: read again
    page = client.get(f"/bills/{sha}?kind=electricity&reread=1")
    assert len(fake.calls) == 3 and "Re-read with the engine" in page.text
