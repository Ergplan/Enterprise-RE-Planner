"""The HTTP API (build prompt section 6, Stage 2.1): contract 1.0 exactly in `esgos-1.0`
mode, contract 1.1 on top in `esgos-1.1` mode. The five contract calls and nothing else
under /v1; /metrics outside it, same token.

Every request carries `Authorization: Bearer <BILLX_TOKEN>` (compared in constant time).
Errors are contract section 8's table from one handler. `X-Request-Id` is echoed and, with
the `traceparent` trace id, written on every log line. Logs carry ids, hashes, timings and
check ids only (invariant 9): a bill value never reaches a log, a metric or an error body.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from billx.core.schema import ENGINE_VERSION, SCHEMA_VERSION
from billx.core.settings import setting
from billx.platform.api.render import render_envelope, render_text
from billx.platform.store import Settings as StoreSettings
from billx.platform.store.files import FileStore
from billx.platform.store.jobs import Job, JobStore, RequestIdConflict
from billx.platform.store.queue import Queue, QueueFull
from billx.platform.store.sweeper import Sweeper

log = logging.getLogger("billx.api")

MODES = ("esgos-1.0", "esgos-1.1")
MEDIA_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/webp": ".webp",
    "image/tiff": ".tiff",
}
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 30
OPTIONS_1_0 = {
    "request_id",
    "product",
    "kind",
    "bill_type",
    "allow_cloud_model",
    "max_cost_usd",
    "hints",
}
OPTIONS_1_1 = OPTIONS_1_0 | {"contact", "account_ref", "pdf_password", "wait"}
_REQUEST_ID = re.compile(r"^[\x21-\x7e]{1,64}$")
_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")


_FILE = File(...)  # the multipart parts of contract 4.2
_OPTIONS = Form(...)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


@dataclass
class ApiSettings:
    mode: str = "esgos-1.1"
    token: str = ""
    data_dir: Path = Path("/data")
    max_jobs: int = 4
    queue_limit: int = 32
    retention_hours: int = 24
    wait_seconds: int = 50
    profiles_version: str = "2026-10-12"

    @classmethod
    def from_env(cls) -> ApiSettings:
        store = StoreSettings.from_env()
        mode = setting("BILLX_API_MODE", "esgos-1.1") or "esgos-1.1"
        if mode not in MODES:
            raise RuntimeError(f"BILLX_API_MODE must be one of {MODES}; got {mode!r}")
        token = setting("BILLX_TOKEN") or ""
        if not token:
            raise RuntimeError("BILLX_TOKEN is not set")
        return cls(
            mode=mode,
            token=token,
            data_dir=store.data_dir,
            max_jobs=store.max_jobs,
            queue_limit=store.queue_limit,
            retention_hours=store.retention_hours,
        )


@dataclass
class Metrics:
    """Counts and timings only (invariant 9)."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    requests: dict[str, int] = field(default_factory=dict)
    jobs_by_status: dict[str, int] = field(default_factory=dict)
    seconds: list[Decimal] = field(default_factory=list)

    def count(self, name: str) -> None:
        with self.lock:
            self.requests[name] = self.requests.get(name, 0) + 1

    def job(self, status: str, seconds: Decimal | None = None) -> None:
        with self.lock:
            self.jobs_by_status[status] = self.jobs_by_status.get(status, 0) + 1
            if seconds is not None:
                self.seconds.append(seconds)

    def render(self, queue: Queue) -> str:
        with self.lock:
            lines = ["# TYPE billx_requests_total counter"]
            lines += [
                f'billx_requests_total{{call="{k}"}} {v}' for k, v in sorted(self.requests.items())
            ]
            lines.append("# TYPE billx_jobs_total counter")
            lines += [
                f'billx_jobs_total{{status="{k}"}} {v}'
                for k, v in sorted(self.jobs_by_status.items())
            ]
            lines.append("# TYPE billx_job_seconds_sum counter")
            lines.append(f"billx_job_seconds_sum {sum(self.seconds, Decimal(0))}")
            lines.append("# TYPE billx_queue_depth gauge")
            lines.append(f"billx_queue_depth {queue.depth()}")
            lines.append("# TYPE billx_jobs_running gauge")
            lines.append(f"billx_jobs_running {queue.running()}")
        return "\n".join(lines) + "\n"


# option validation --------------------------------------------------------------------------


def _decimal_string(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ApiError(422, "invalid_options", "max_cost_usd must be a decimal string")
    try:
        d = Decimal(value)
    except InvalidOperation:
        raise ApiError(422, "invalid_options", "max_cost_usd is not a decimal") from None
    if d < 0:
        raise ApiError(422, "invalid_options", "max_cost_usd must not be negative")
    return d


def validate_options(raw: str, mode: str) -> dict:
    """Contract 4.2's options table; a 1.1 option in 1.0 mode is `bad_request` (6.1)."""
    try:
        options = json.loads(raw)
    except ValueError:
        raise ApiError(400, "bad_request", "options is not JSON") from None
    if not isinstance(options, dict):
        raise ApiError(400, "bad_request", "options must be a JSON object")
    allowed = OPTIONS_1_0 if mode == "esgos-1.0" else OPTIONS_1_1
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise ApiError(400, "bad_request", f"unknown options: {', '.join(unknown)}")
    request_id = options.get("request_id")
    if not isinstance(request_id, str) or not _REQUEST_ID.match(request_id):
        raise ApiError(400, "bad_request", "request_id is required (up to 64 characters)")
    if not isinstance(options.get("product"), str) or not options["product"]:
        raise ApiError(400, "bad_request", "product is required")
    kind = options.get("kind", "bill")
    if kind not in ("bill", "text"):
        raise ApiError(422, "invalid_options", "kind must be bill or text")
    bill_type = options.get("bill_type", "auto")
    if bill_type not in ("electricity", "gas", "auto"):
        raise ApiError(422, "invalid_options", "bill_type must be electricity, gas or auto")
    allow = options.get("allow_cloud_model")
    if not isinstance(allow, bool):
        raise ApiError(422, "invalid_options", "allow_cloud_model is required (true or false)")
    max_cost = Decimal(0)
    if allow:
        if "max_cost_usd" not in options:
            raise ApiError(
                422, "invalid_options", "max_cost_usd is required when allow_cloud_model is true"
            )
        max_cost = _decimal_string(options["max_cost_usd"])
    elif "max_cost_usd" in options:
        max_cost = _decimal_string(options["max_cost_usd"])
    hints = options.get("hints", {})
    if not isinstance(hints, dict) or any(not isinstance(v, str) for v in hints.values()):
        raise ApiError(422, "invalid_options", "hints must be an object of strings")
    if "wait" in options and not isinstance(options["wait"], bool):
        raise ApiError(422, "invalid_options", "wait must be a boolean")
    if "contact" in options and not isinstance(options["contact"], dict):
        raise ApiError(422, "invalid_options", "contact must be an object")
    if "pdf_password" in options and not isinstance(options["pdf_password"], str):
        raise ApiError(422, "invalid_options", "pdf_password must be a string")
    return {
        "request_id": request_id,
        "product": options["product"],
        "kind": kind,
        "bill_type": bill_type,
        "allow_cloud_model": allow,
        "max_cost_usd": format(max_cost, "f"),
        "hints": hints,
        "contact": options.get("contact"),
        "account_ref": options.get("account_ref"),
        "wait": bool(options.get("wait", False)),
        # pdf_password is used once and never stored: it is handed to the job's process
        # call in memory only (deferred: contract 1.0 has no password option; 1.1 accepts it)
    }


# the app ------------------------------------------------------------------------------------


ReadFile = Callable[..., Any]


def create_app(
    settings: ApiSettings,
    *,
    read_file: ReadFile | None = None,
    read_text_file: ReadFile | None = None,
    providers: Callable[[], tuple[Any, Any]] | None = None,
    start_workers: bool = True,
) -> FastAPI:
    app = FastAPI(title="billx", docs_url=None, redoc_url=None, openapi_url=None)
    mode = settings.mode
    store = JobStore(settings.data_dir)
    files = FileStore(settings.data_dir)
    metrics = Metrics()
    passwords: dict[str, str] = {}  # job id -> pdf_password, held in memory only, used once

    def _providers():
        if providers is not None:
            return providers()
        from billx.reader.providers.base import make_model_a, make_model_b

        return make_model_a(), make_model_b()

    def _third_reader():
        """LlamaParse beside Model A, only with the engine's own providers (a test that
        injects providers gets none) and a key."""
        if providers is not None:
            return None
        from billx.reader.providers.base import make_model_c

        return make_model_c()

    def _read_file(*args, **kwargs):
        if read_file is not None:
            return read_file(*args, **kwargs)
        from billx.reader.pipeline import read_file as real

        return real(*args, **kwargs)

    def _read_text(path):
        if read_text_file is not None:
            return read_text_file(path)
        from billx.reader.pipeline import read_text_file as real

        return real(path)

    def process(job: Job) -> None:
        """Runs on a worker thread: read, render in this mode, store the result."""
        from billx.reader.pipeline import ReadError

        started = time.monotonic()
        options = job.options
        path = files.input_path(job.job_id)
        try:
            if options["kind"] == "text":
                rendered = render_text(_read_text(path), mode)
            else:
                allow = bool(options["allow_cloud_model"])
                model_a, model_b = _providers() if allow else (None, None)
                extra = {}
                model_c = _third_reader() if allow else None
                if model_c is not None:
                    extra["model_c"] = model_c
                env = _read_file(
                    path,
                    allow_cloud_model=allow,
                    max_cost_usd=Decimal(options["max_cost_usd"]),
                    model_a=model_a,
                    model_b=model_b,
                    contract="1.0" if mode == "esgos-1.0" else "1.1",
                    hints=options.get("hints") or {},
                    **extra,
                )
                rendered = render_envelope(env, mode)
        except ReadError as exc:
            store.mark_failed(job.job_id, exc.code, exc.code)
            metrics.job("failed")
            log.info("job=%s failed code=%s", job.job_id, exc.code)
            return
        finally:
            passwords.pop(job.job_id, None)
        files.write_result(job.job_id, json.dumps(rendered, ensure_ascii=False))
        store.mark_done(job.job_id, str(files.result_path(job.job_id)))
        seconds = Decimal(str(round(time.monotonic() - started, 3)))
        metrics.job("done", seconds)
        statuses = [
            b.get("status", "passed" if b.get("passed") else "failed")
            for b in rendered.get("bills", [])
        ]
        log.info("job=%s done seconds=%s bills=%s", job.job_id, seconds, ",".join(statuses))

    queue = Queue(store, process, max_jobs=settings.max_jobs, queue_limit=settings.queue_limit)
    sweeper = Sweeper(store, files, retention_hours=settings.retention_hours)
    app.state.store, app.state.files, app.state.queue, app.state.metrics = (
        store,
        files,
        queue,
        metrics,
    )

    @app.on_event("startup")
    def _startup() -> None:
        queue.recover()  # jobs left queued or reading by a crash go back to the queue
        if start_workers:
            queue.start()
            sweeper.start()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        queue.stop(timeout=5)
        sweeper.stop()

    # auth, ids and errors ---------------------------------------------------------------

    def _authorised(request: Request) -> bool:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(token, settings.token)

    @app.middleware("http")
    async def _ids_and_auth(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        trace = _TRACEPARENT.match(request.headers.get("traceparent", ""))
        request.state.request_id = request_id
        request.state.trace_id = trace.group(1) if trace else None
        if not _authorised(request):
            response = _error_response(401, "unauthorised", "missing or wrong token")
        else:
            response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        log.info(
            "request_id=%s trace_id=%s %s %s -> %d",
            request_id,
            request.state.trace_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response

    def _error_response(status: int, code: str, message: str, headers: dict | None = None):
        return JSONResponse(
            {"error": {"code": code, "message": message}}, status_code=status, headers=headers
        )

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return _error_response(exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception):
        log.error(
            "request_id=%s internal %s",
            getattr(request.state, "request_id", "-"),
            type(exc).__name__,
        )
        return _error_response(500, "internal", "internal error; see the request id in the log")

    # calls ---------------------------------------------------------------------------------

    @app.get("/v1/health")
    def health():
        metrics.count("health")
        from billx.reader import ocr

        model_a, model_b = _providers()
        return {
            "status": "ok",
            "engine_version": ENGINE_VERSION,
            "contract_version": "1.0" if mode == "esgos-1.0" else "1.1",
            "schema_version": SCHEMA_VERSION,
            "profiles_version": settings.profiles_version,
            "ocr": "ready" if ocr.available() else "unavailable",
            "cloud_model": "configured" if (model_a or model_b) else "not_configured",
        }

    @app.post("/v1/jobs", status_code=202)
    async def create_job(request: Request, file: UploadFile = _FILE, options: str = _OPTIONS):
        metrics.count("jobs_create")
        opts = validate_options(options, mode)
        media_type = (file.content_type or "").split(";")[0].strip().lower()
        suffix = MEDIA_TYPES.get(media_type) or _suffix_from_name(file.filename or "")
        if suffix is None:
            raise ApiError(415, "unsupported_type", "not one of the file types in contract 4.2")
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise ApiError(413, "too_large", "over 25 MB")
        sha = _sha256(data)
        try:
            job, created = store.create(
                request_id=opts["request_id"],
                product=opts["product"],
                sha256=sha,
                media_type=_media_type_for(suffix),
                size=len(data),
                kind=opts["kind"],
                options={k: v for k, v in opts.items() if k != "contact"}
                | {"contact": opts.get("contact")},
            )
        except RequestIdConflict:
            raise ApiError(409, "conflict", "request_id reused with a different file") from None
        if created:
            files.put(job.job_id, data, suffix)
            pages = _page_count(files.input_path(job.job_id), suffix)
            if pages is not None and pages > MAX_PAGES:
                files.delete(job.job_id)
                store.delete(job.job_id)
                raise ApiError(413, "too_large", "over 30 pages")
            try:
                queue.submit(job)
            except QueueFull as exc:
                files.delete(job.job_id)
                store.delete(job.job_id)
                raise ApiError(
                    429, "busy", "the queue is full", {"Retry-After": str(exc.retry_after_seconds)}
                ) from None
            log.info(
                "job=%s created sha=%s kind=%s product=%s",
                job.job_id,
                sha[:12],
                opts["kind"],
                opts["product"],
            )
        body = {"job_id": job.job_id, "status": job.status}
        if opts.get("wait") and mode == "esgos-1.1":
            deadline = time.monotonic() + settings.wait_seconds
            while time.monotonic() < deadline:
                current = store.get(job.job_id)
                if current is not None and current.status in ("done", "failed"):
                    return JSONResponse(_job_body(current), status_code=200)
                time.sleep(0.2)
        return JSONResponse(body, status_code=202)

    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str):
        metrics.count("jobs_get")
        job = store.get(job_id)
        if job is None:
            raise ApiError(404, "not_found", "unknown job")
        return _job_body(job)

    def _job_body(job: Job) -> dict:
        result = None
        if job.status == "done":
            text = files.read_result(job.job_id)
            result = json.loads(text) if text else None
        error = None
        if job.status == "failed":
            error = {"code": job.error_code or "internal", "message": job.error_message or ""}
        return {
            "job_id": job.job_id,
            "request_id": job.request_id,
            "status": job.status,
            "submitted_at": job.submitted_at,
            "finished_at": job.finished_at,
            "error": error,
            "result": result,
        }

    @app.delete("/v1/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str):
        metrics.count("jobs_delete")
        if store.get(job_id) is None:
            raise ApiError(404, "not_found", "unknown job")
        files.delete(job_id)
        store.delete(job_id)
        passwords.pop(job_id, None)
        return Response(status_code=204)

    @app.post("/v1/feedback", status_code=202)
    async def feedback(request: Request):
        metrics.count("feedback")
        try:
            body = json.loads(await request.body())
        except ValueError:
            raise ApiError(400, "bad_request", "body is not JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get("corrections"), list):
            raise ApiError(400, "bad_request", "job_id and corrections are required")
        job_id = body.get("job_id")
        job = store.get(job_id) if isinstance(job_id, str) else None
        if job is None:
            raise ApiError(404, "not_found", "unknown job")
        # Kept: the path, whether the value was right (engine == final), and the job's hash
        # and profile; the values themselves go with the job's folder within 24 hours.
        kept = []
        for c in body["corrections"]:
            if not isinstance(c, dict) or "path" not in c:
                raise ApiError(400, "bad_request", "each correction needs a path")
            kept.append(
                {"path": str(c["path"]), "right": c.get("engine_value") == c.get("final_value")}
            )
        files.append_feedback(
            job.job_id, {"bill_index": body.get("bill_index", 0), "corrections": kept}
        )
        log.info("job=%s feedback paths=%d", job.job_id, len(kept))
        return {"accepted": len(kept)}

    @app.get("/metrics")
    def prometheus():
        return Response(metrics.render(queue), media_type="text/plain; version=0.0.4")

    return app


def _suffix_from_name(name: str) -> str | None:
    lower = name.lower()
    for suffix in (".pdf", ".jpg", ".jpeg", ".png", ".heic", ".webp", ".tif", ".tiff"):
        if lower.endswith(suffix):
            return ".jpg" if suffix == ".jpeg" else (".tiff" if suffix == ".tif" else suffix)
    return None


def _media_type_for(suffix: str) -> str:
    return next(m for m, s in MEDIA_TYPES.items() if s == suffix)


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _page_count(path: Path, suffix: str) -> int | None:
    if suffix != ".pdf":
        return None
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(path))
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:  # noqa: BLE001 - an unreadable PDF is reported by the reader, not here
        return None
