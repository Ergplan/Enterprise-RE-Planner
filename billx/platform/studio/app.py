"""Studio confirmation mode (Stage 0.5): a person confirms each guaranteed field of a bill
against its page images, and the confirmed values go to the golden manifest.

Plain server-rendered HTML, served on 127.0.0.1 only (see cli.py). Logs carry bill hashes,
counts and timings, never a value.
"""

import html
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, unquote

import pypdfium2 as pdfium
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from billx.core.schema import Envelope
from billx.core.settings import load_config, setting
from billx.platform.studio import golden
from billx.platform.studio.workspace import Workspace
from billx.reader.providers.base import Page, model_a_spec

log = logging.getLogger(__name__)

BILL_KINDS = ("electricity", "gas")
INPUT_KINDS = ("digital_pdf", "scan", "photo")
NOT_PRINTED = "not_printed"

e = html.escape


def load_fields(bill_kind: str) -> tuple[str, list[dict]]:
    cfg = load_config("guaranteed_fields.yaml")
    # arrays (readings[], energy.tod[], charges.by_code[]) are confirmed through the
    # element and meter tables (Stage 3.3), not as single fields
    return str(cfg["version"]), [f for f in cfg[bill_kind] if f["type"] != "array"]


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


CSS = """
body{font:14px/1.4 system-ui,sans-serif;margin:0;color:#1d1d1f;background:#fafafa}
header{padding:10px 16px;background:#1d3557;color:#fff;display:flex;gap:16px;align-items:center}
header a{color:#fff}
main{padding:16px}
table{border-collapse:collapse;background:#fff}
td,th{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:middle}
.bill{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
@media (max-width:900px){.bill{grid-template-columns:minmax(0,1fr)}}
.pages{max-height:calc(100vh - 80px);overflow:auto;background:#eee;padding:8px}
.pages img{width:100%;display:block;margin-bottom:8px;background:#fff}
.fields{max-height:calc(100vh - 80px);overflow:auto}
.fields table{width:100%}
.fields td{overflow-wrap:anywhere}
.fields label{display:block;margin:4px 0}
.pf{font-family:ui-monospace,monospace;color:#555}
.vf{padding:0 4px;border-radius:3px;background:#eee}.vf.verified{background:#d4edda}
.vf.disputed{background:#f8d7da}.vf.unverified{background:#fff3cd}
.checks{padding-left:16px}.checks li.fail{color:#a00}.checks li.warn{color:#8a6d00}
.v{width:100%;min-width:7em;box-sizing:border-box;font-family:ui-monospace,monospace}
.note{background:#fff3cd;padding:6px 8px}
.err{background:#f8d7da;padding:6px 8px}
.ok{color:#2a7a2a}
button{padding:6px 14px;font-size:14px}
"""


def _page(title: str, body: str, confirmer: str | None = None, status_code: int = 200):
    who = (
        f'<span>Confirming as <b>{e(confirmer)}</b> · <a href="/session">change</a></span>'
        if confirmer
        else ""
    )
    doc = (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{e(title)}</title>"
        f"<style>{CSS}</style></head><body><header><b><a href='/'>billx studio</a></b>"
        f"{who}</header><main>{body}</main></body></html>"
    )
    return HTMLResponse(doc, status_code=status_code)


def engine_reader(path: Path, allow_cloud: bool) -> Envelope:
    """The default pre-fill: the engine's own reading of the bill (two-reader pre-fill,
    build prompt section 8), with the model readers only when the session allows them and
    a key is configured."""
    from billx.reader.pipeline import read_file
    from billx.reader.providers.base import make_model_a, make_model_b

    model_a, model_b = (make_model_a(), make_model_b()) if allow_cloud else (None, None)
    return read_file(
        path,
        allow_cloud_model=allow_cloud,
        max_cost_usd=Decimal(str(load_config("studio.yaml").get("max_cost_usd", "1.00"))),
        model_a=model_a,
        model_b=model_b,
    )


def engine_fingerprint(allow_cloud: bool) -> str:
    """What a cached pre-fill was read with. Any change (a new engine or prompt version, an
    edited model, price or profile file, a key added or removed, cloud use allowed or not)
    makes the studio read the bill again instead of showing a stale reading."""
    import hashlib

    from billx.core.schema import ENGINE_VERSION
    from billx.core.settings import config_dir

    root = Path(__file__).resolve().parents[3]
    h = hashlib.sha256()
    h.update(f"{ENGINE_VERSION}|cloud={allow_cloud}".encode())
    for name in (
        "BILLX_OPENAI_API_KEY",
        "BILLX_ANTHROPIC_API_KEY",
        "BILLX_MODEL_A",
        "BILLX_MODEL_B",
    ):
        h.update(f"|{name}={bool(setting(name))}".encode())
    if allow_cloud:
        for name in ("BILLX_MODEL_A", "BILLX_MODEL_B"):
            h.update(f"|{setting(name) or ''}".encode())
    files = [config_dir() / n for n in ("providers.yaml", "guaranteed_fields.yaml")]
    files += sorted((root / "billx" / "reader" / "prompts").glob("*.md"))
    files += sorted((root / "profiles").rglob("*.yaml"))
    for f in files:
        if f.is_file():
            h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def cloud_configured() -> bool:
    """Whether a model key is present (presence only; the value is never read here)."""
    return bool(setting("BILLX_OPENAI_API_KEY") or setting("BILLX_ANTHROPIC_API_KEY"))


def create_app(
    workspace: Workspace,
    reader: Callable[[Path, bool], Envelope] = engine_reader,
) -> FastAPI:
    app = FastAPI(title="billx studio", docs_url=None, redoc_url=None, openapi_url=None)
    ws = workspace

    def confirmer_of(request: Request) -> str | None:
        raw = request.cookies.get("confirmer")
        return unquote(raw) if raw else None

    def cloud_allowed(request: Request) -> bool:
        return request.cookies.get("allow_cloud", "1") == "1"

    # session ------------------------------------------------------------------------

    def session_form(request: Request) -> HTMLResponse:
        checked = "checked" if cloud_allowed(request) else ""
        name = e(confirmer_of(request) or "")
        body = f"""
<h2>Who is confirming?</h2>
<form method="post" action="/session">
<label>Your name <input name="confirmer" value="{name}" required autofocus></label>
<label><input type="checkbox" name="allow_cloud" value="1" {checked}>
 Allow cloud model for pre-fill ({e(model_a_spec())}). Unticked, no file leaves this machine
 and the pre-fill is empty.</label>
<button>Start</button></form>"""
        return _page("billx studio", body)

    @app.get("/session", response_class=HTMLResponse)
    def get_session(request: Request):
        return session_form(request)

    @app.post("/session")
    def post_session(confirmer: str = Form(...), allow_cloud: str | None = Form(None)):
        name = confirmer.strip()
        if not name:
            return RedirectResponse("/session", status_code=303)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("confirmer", quote(name), httponly=True, samesite="strict")
        resp.set_cookie("allow_cloud", "1" if allow_cloud else "0", samesite="strict")
        return resp

    # overview -----------------------------------------------------------------------

    def overview(request: Request, message: str = "", status_code: int = 200):
        confirmer = confirmer_of(request)
        latest = golden.latest_by_sha()
        bills = ws.bills
        if cloud_allowed(request):
            cloud = (
                f"on ({e(model_a_spec())})"
                if cloud_configured()
                else "allowed, but no model key is configured: local readers only"
            )
        else:
            cloud = "off for this session: local readers only (text layer, OCR)"
        rows = []
        for sha, bill in bills.items():
            entry = latest.get(sha)
            status = (
                f"<span class='ok'>confirmed by {e(entry['confirmed_by'])}, "
                f"{entry['seconds']} s</span>"
                if entry
                else "not confirmed"
            )
            rows.append(
                f"<tr><td><a href='/bills/{sha}'>{e(bill['name'])}</a></td>"
                f"<td>{e(bill['input_kind'])}</td><td>{status}</td>"
                f"<td><code>{sha[:12]}</code></td></tr>"
            )
        done = sum(1 for sha in bills if sha in latest)
        sources = "".join(f"<li><code>{e(s)}</code></li>" for s in ws.sources) or "<li>none</li>"
        msg = f"<p class='note'>{e(message)}</p>" if message else ""
        body = f"""
<h2>Workspace {e(ws.name)}</h2>{msg}
<p>Cloud pre-fill: {cloud} · <a href="/session">change</a></p>
<h3>Source folders</h3><ul>{sources}</ul>
<form method="post" action="/sources"><label>Add a folder of bills (PDF, JPEG, PNG)
<input name="folder" size="60" placeholder="/Users/you/bills/avvnl" required></label>
<button>Add</button></form>
<h3>Bills ({done} of {len(bills)} confirmed)</h3>
<table><tr><th>File</th><th>Input kind (guess)</th><th>Status</th><th>sha256</th></tr>
{"".join(rows) or "<tr><td colspan=4>No bills yet: add a folder above.</td></tr>"}</table>"""
        return _page("billx studio", body, confirmer, status_code)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, added: int | None = None):
        if not confirmer_of(request):
            return session_form(request)
        message = f"{added} new bill(s) added." if added is not None else ""
        return overview(request, message)

    @app.post("/sources")
    def add_source(request: Request, folder: str = Form(...)):
        try:
            added = ws.add_source(Path(folder.strip()))
        except NotADirectoryError:
            return overview(request, "That folder does not exist.", 400)
        return RedirectResponse(f"/?added={added}", status_code=303)

    # one bill -----------------------------------------------------------------------

    def pages_of(sha: str) -> list[Page]:
        if sha not in ws.bills:
            raise HTTPException(404, "unknown bill")
        try:
            return ws.pages(sha)
        except FileNotFoundError as exc:
            raise HTTPException(410, str(exc)) from None
        except pdfium.PdfiumError:
            raise HTTPException(422, f"bill {sha[:12]}: the PDF cannot be opened") from None

    def prefill_for(
        sha: str, kind: str, allow: bool, pages: list[Page], fresh: bool = False
    ) -> tuple[dict, str]:
        """The cached engine reading, or a new one. The pre-fill holds, per field, the decided
        value (printed text), its verification and every reader's raw string; and the checks.
        A cached reading is used only while its fingerprint (engine and prompt versions, the
        model and profile configuration, which keys exist, whether cloud use was allowed)
        still matches; otherwise, or when `fresh`, the engine reads the bill again."""
        empty = {"model": None, "prompt": None, "values": {}, "fields": {}, "checks": []}
        fingerprint = engine_fingerprint(allow)
        cached = ws.cached_prefill(sha, kind)
        if cached is not None and not fresh and cached.get("fingerprint") == fingerprint:
            return cached, ""
        try:
            envelope = reader(ws.path_of(sha), allow)
        except Exception as exc:  # the studio must stay usable: a person types the values
            log.warning("engine reading failed bill=%s: %s", sha[:12], type(exc).__name__)
            return empty, "The engine could not read this bill. Type each value from the image."
        bill = envelope.bills[0]
        if bill.bill_type != kind and bill.bill_type is not None:
            note = (
                f"The engine read this as a {bill.bill_type} bill; "
                "pick that kind to see its pre-fill."
            )
        else:
            note = ""
        fields = {}
        values = {}
        for v in bill.fields:
            fields[v.path] = {
                "value": v.value,
                "printed": v.printed,
                "unit": v.unit,
                "verification": v.verification,
                "readers": {r.reader: r.raw for r in v.readings},
            }
            if v.printed:
                values[v.path] = v.printed
        readers = sorted({r.reader for v in bill.fields for r in v.readings})
        prefill = {
            "fingerprint": fingerprint,
            "model": ",".join(readers) or None,
            "prompt": "engine",
            "field_list_version": load_fields(kind)[0],
            "status": bill.status,
            "review_reasons": list(bill.review_reasons),
            "flags": list(bill.flags),
            "checks": [
                {"id": c.id, "status": c.status, "description": c.description}
                for c in bill.checks
                if c.status != "skip"
            ],
            "values": values,
            "fields": fields,
        }
        ws.save_prefill(sha, kind, prefill)
        return prefill, note

    def bill_page(
        request: Request,
        sha: str,
        kind: str,
        pages: list[Page],
        prefill: dict,
        note: str = "",
        form: dict | None = None,
        errors: list[str] | None = None,
        opened_at_ms: int | None = None,
    ):
        bill = ws.bills[sha]
        latest = golden.latest_by_sha()
        last = latest.get(sha)
        _, fields = load_fields(kind)
        pf = prefill["values"]
        start = {
            "discom": last["discom"] if last else "",
            "layout_id": last["layout_id"] if last else "",
            "input_kind": last["input_kind"] if last else bill["input_kind"],
        }
        if form is not None:
            start = {k: form.get(k, "") for k in start}

        def initial(i: int, path: str) -> str:
            if form is not None:
                return form.get(f"v_{i}", "")
            if last and last.get("bill_kind") == kind:
                value = last["fields"].get(path, "")
                return "" if value == NOT_PRINTED else value
            return pf.get(path, "")

        def ticked(name: str) -> str:
            return "checked" if form is not None and form.get(name) else ""

        rows = []
        detail = prefill.get("fields", {})
        for i, f in enumerate(fields):
            req = " *" if f.get("required") else ""
            info = detail.get(f["path"], {})
            shown_unit = info.get("unit") or f.get("unit")  # as the bill prints it
            unit = f" <small>{e(shown_unit)}</small>" if shown_unit else ""
            shown = e(pf[f["path"]]) if f["path"] in pf else "—"
            readers = info.get("readers", {})
            seen = " ".join(f"<small>{e(k)}: {e(v)}</small>" for k, v in readers.items())
            badge = info.get("verification", "")
            if readers:
                shown = f"{shown}<br><span class='vf {e(badge)}'>{e(badge)}</span> {seen}"
            rows.append(
                f"<tr><td><code>{e(f['path'])}</code>{unit}{req}</td><td class='pf'>{shown}</td>"
                f"<td><input class='v' name='v_{i}' value='{e(initial(i, f['path']))}'></td>"
                f"<td><input type='checkbox' class='c' name='c_{i}' value='1' "
                f"{ticked(f'c_{i}')}></td>"
                f"<td><input type='checkbox' class='np' name='np_{i}' value='1' "
                f"{ticked(f'np_{i}')}></td></tr>"
            )
        kinds = "".join(
            f"<option {'selected' if k == kind else ''}>{k}</option>" for k in BILL_KINDS
        )
        input_kinds = "".join(
            f"<option {'selected' if k == start['input_kind'] else ''}>{k}</option>"
            for k in INPUT_KINDS
        )
        discoms = sorted({x["discom"] for x in latest.values() if x.get("discom")})
        datalist = "".join(f"<option value='{e(d)}'>" for d in discoms)
        images = "".join(
            f"<img src='/bills/{sha}/pages/{n}' alt='page {n + 1}'>" for n in range(len(pages))
        )
        notes = f"<p class='note'>{e(note)}</p>" if note else ""
        notes += (
            f"<p><a href='/bills/{sha}?kind={e(kind)}&amp;reread=1'>Re-read with the engine</a>"
            " <small>(reads the bill again with the current engine and keys; about a minute "
            "for a scan)</small></p>"
        )
        if prefill.get("checks"):
            checks = "".join(
                f"<li class='{e(c['status'])}'>{e(c['status'])} <b>{e(c['id'])}</b> "
                f"{e(c['description'])}</li>"
                for c in prefill["checks"]
            )
            reasons = ", ".join(prefill.get("review_reasons", []) + prefill.get("flags", []))
            notes += (
                f"<details><summary>Engine: <b>{e(prefill.get('status', ''))}</b>"
                f"{' · ' + e(reasons) if reasons else ''}</summary>"
                f"<ul class='checks'>{checks}</ul></details>"
            )
        if errors:
            notes += (
                "<p class='err'>Not saved. Confirm, type, or mark not printed: "
                + ", ".join(f"<code>{e(p)}</code>" for p in errors)
                + "</p>"
            )
        if last:
            notes += (
                f"<p class='note'>Already confirmed by {e(last['confirmed_by'])}; saving again "
                "appends a correction that supersedes it.</p>"
            )
        opened = opened_at_ms if opened_at_ms is not None else _now_ms()
        body = f"""
<div class="bill"><div class="pages">{images}</div>
<form method="post" class="fields" action="/bills/{sha}">
<h3>{e(bill["name"])} <small><code>{sha[:12]}</code></small></h3>{notes}
<label>Bill kind <select name="kind"
 onchange="location.href='/bills/{sha}?kind='+this.value">{kinds}</select></label>
<label>Discom <input name="discom" list="discoms" value="{e(start["discom"])}" required></label>
<datalist id="discoms">{datalist}</datalist>
<label>Layout id <input name="layout_id" value="{e(start["layout_id"])}"
 placeholder="avvnl-ht-2024" required></label>
<label>Input kind <select name="input_kind">{input_kinds}</select></label>
<input type="hidden" name="opened_at_ms" value="{opened}">
<p>Tick <b>confirm</b> when the value matches the image (one click), or type the value as
printed. Tick <b>not printed</b> when the bill does not show the field. * required field.</p>
<table><tr><th>Field</th><th>Pre-fill</th><th>Value as printed</th><th>Confirm</th>
<th>Not printed</th></tr>{"".join(rows)}</table>
<p><button>Save</button></p></form></div>
<script>
document.querySelectorAll('.fields tr').forEach(function(tr){{
  var v=tr.querySelector('.v'),c=tr.querySelector('.c'),np=tr.querySelector('.np');
  if(!v)return;
  v.addEventListener('input',function(){{c.checked=v.value.trim()!=='';np.checked=false;}});
  np.addEventListener('change',function(){{if(np.checked)c.checked=false;}});
  c.addEventListener('change',function(){{if(c.checked)np.checked=false;}});
}});
</script>"""
        status = 400 if errors else 200
        return _page(bill["name"], body, confirmer_of(request), status)

    @app.get("/bills/{sha}", response_class=HTMLResponse)
    def open_bill(request: Request, sha: str, kind: str | None = None, reread: int = 0):
        if not confirmer_of(request):
            return RedirectResponse("/", status_code=303)
        pages = pages_of(sha)
        if kind not in BILL_KINDS:
            last = golden.latest_by_sha().get(sha)
            kind = last["bill_kind"] if last else "electricity"
        prefill, note = prefill_for(sha, kind, cloud_allowed(request), pages, fresh=bool(reread))
        return bill_page(request, sha, kind, pages, prefill, note)

    @app.get("/bills/{sha}/pages/{n}")
    def page_image(sha: str, n: int):
        pages = pages_of(sha)
        if not 0 <= n < len(pages):
            raise HTTPException(404, "no such page")
        return Response(pages[n].data, media_type=pages[n].mime)

    @app.post("/bills/{sha}")
    async def save_bill(request: Request, sha: str):
        confirmer = confirmer_of(request)
        if not confirmer:
            return RedirectResponse("/", status_code=303)
        pages = pages_of(sha)
        form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
        kind = form.get("kind", "")
        if kind not in BILL_KINDS:
            raise HTTPException(400, "unknown bill kind")
        version, fields = load_fields(kind)
        prefill = ws.cached_prefill(sha, kind) or {"model": None, "prompt": None, "values": {}}

        errors, values = [], {}
        for name in ("discom", "layout_id"):
            if not form.get(name, "").strip():
                errors.append(name)
        if form.get("input_kind") not in INPUT_KINDS:
            errors.append("input_kind")
        for i, f in enumerate(fields):
            typed = form.get(f"v_{i}", "").strip()
            if form.get(f"np_{i}"):
                values[f["path"]] = NOT_PRINTED
            elif form.get(f"c_{i}") and typed:
                values[f["path"]] = typed
            else:
                errors.append(f["path"])
        try:
            opened_at_ms = int(form.get("opened_at_ms", ""))
        except ValueError:
            raise HTTPException(400, "missing opened_at_ms") from None
        if errors:
            log.info("save refused bill=%s missing=%d", sha[:12], len(errors))
            return bill_page(
                request, sha, kind, pages, prefill, "", form, errors, opened_at_ms=opened_at_ms
            )

        pf = prefill["values"]
        matched = [
            path
            for path, value in values.items()
            if pf.get(path) == value
            or (prefill["model"] and value == NOT_PRINTED and path not in pf)
        ]
        seconds = max(0, (_now_ms() - opened_at_ms + 500) // 1000)
        entry = golden.append_entry(
            {
                "sha256": sha,
                "source_path": ws.bills[sha]["path"],
                "workspace": ws.name,
                "discom": form["discom"].strip(),
                "layout_id": form["layout_id"].strip(),
                "input_kind": form["input_kind"],
                "bill_kind": kind,
                "field_list_version": version,
                "fields": values,
                "prefill_model": prefill["model"],
                "prefill_prompt": prefill["prompt"],
                "matched_prefill": matched,
                "confirmed_by": confirmer,
                "seconds": seconds,
                "confirmed_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "split": golden.recorded_split(sha),
            }
        )
        log.info(
            "confirmed bill=%s fields=%d matched=%d seconds=%d",
            sha[:12],
            len(values),
            len(matched),
            entry["seconds"],
        )
        latest = golden.latest_by_sha()
        nxt = next((s for s in ws.bills if s not in latest), None)
        return RedirectResponse(f"/bills/{nxt}" if nxt else "/", status_code=303)

    return app
