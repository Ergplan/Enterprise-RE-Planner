"""The evaluation runner: every case through the engine, sequentially, with timing.

`billx eval` calls `evaluate_synthetic(folder, read_file, ...)` or `evaluate_golden(read_file,
...)`, prints `result.summary()`, writes `write_report(result, path)` and exits with
`result.ok()`. The engine entry point is `billx.reader.pipeline.read_file(path, *,
allow_cloud_model, max_cost_usd, model_a=None, model_b=None) -> Envelope`; it is imported
lazily when `read_file` is None, so the evaluation is tested with an injected fake and the
platform never imports the reader at import time. An exception from the engine is recorded
by its class name only (never its message, which could carry a value) and the run continues.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from billx.core.schema import ENGINE_VERSION
from billx.platform.evals.manifest import (
    EvalCase,
    SetKind,
    load_golden,
    load_synthetic,
    synthetic_set_name,
)
from billx.platform.evals.metrics import Metrics, Outcome, compute, field_types, outcome
from billx.platform.evals.report import render_markdown, write_report
from billx.platform.evals.report import summary as _summary

if TYPE_CHECKING:
    from billx.core.schema import Envelope

ReadFile = Callable[..., "Envelope"]
log = logging.getLogger("billx.evals")


@dataclass(frozen=True)
class CaseResult:
    case: EvalCase
    envelope: Envelope | None
    error: str | None  # the exception's class name; never its message
    seconds: Decimal
    cost_usd: Decimal


@dataclass(frozen=True)
class EvalResult:
    set_name: str
    set_kind: SetKind
    date: str
    engine_version: str
    allow_cloud_model: bool
    max_cost_usd: Decimal
    results: tuple[CaseResult, ...]
    outcomes: tuple[Outcome, ...]
    metrics: Metrics

    @property
    def unmeasured(self) -> bool:
        """A real set is `unmeasured` until a held-out set exists (section 10)."""
        return self.set_kind == "golden"

    def summary(self) -> dict:
        """The JSON summary (counts, rates as strings, ids and paths; no value)."""
        return _summary(self)

    def markdown(self) -> str:
        return render_markdown(self)

    def ok(self) -> bool:
        """What `main` demands of every commit (section 10): no silent error, no false
        refusal, no non-bill read as a bill, no engine error, every planted misread caught."""
        t = self.metrics.total
        return (
            t.silent_errors == 0
            and t.false_refusals == 0
            and t.non_bills_read_as_bills == 0
            and t.errors == 0
            and t.planted_missed == 0
        )


def _engine_read_file() -> ReadFile:
    from billx.reader.pipeline import read_file  # lazy: the integrator provides it

    return read_file


def _cost(envelope: Envelope | None) -> Decimal:
    if envelope is None:
        return Decimal(0)
    return sum((u.cost_usd for u in envelope.usage), Decimal(0))


def run_case(
    case: EvalCase, read_file: ReadFile, *, allow_cloud_model: bool, max_cost_usd: Decimal
) -> CaseResult:
    started = time.perf_counter()
    envelope: Envelope | None = None
    error: str | None = None
    try:
        envelope = read_file(
            Path(case.path), allow_cloud_model=allow_cloud_model, max_cost_usd=max_cost_usd
        )
    except Exception as exc:  # noqa: BLE001 - the run continues; the class name is recorded
        error = type(exc).__name__
    seconds = Decimal(f"{time.perf_counter() - started:.3f}")
    log.info("eval case=%s error=%s seconds=%s", case.id, error or "-", seconds)  # ids only
    return CaseResult(case, envelope, error, seconds, _cost(envelope))


def run(
    cases: Iterable[EvalCase],
    read_file: ReadFile | None = None,
    *,
    allow_cloud_model: bool,
    max_cost_usd: Decimal,
    set_name: str = "set",
    set_kind: SetKind = "synthetic",
    date: str | None = None,
) -> EvalResult:
    """Run every case through `read_file` (the engine's when None), in order, and compute
    the metrics. `date` (ISO) is for repeatable reports; the default is today, UTC."""
    reader = read_file or _engine_read_file()
    types = field_types()
    results: list[CaseResult] = []
    outcomes: list[Outcome] = []
    for case in cases:
        r = run_case(case, reader, allow_cloud_model=allow_cloud_model, max_cost_usd=max_cost_usd)
        results.append(r)
        outcomes.append(outcome(case, r.envelope, r.seconds, r.error, types))
    return EvalResult(
        set_name=set_name,
        set_kind=set_kind,
        date=date or datetime.now(UTC).date().isoformat(),
        engine_version=ENGINE_VERSION,
        allow_cloud_model=allow_cloud_model,
        max_cost_usd=max_cost_usd,
        results=tuple(results),
        outcomes=tuple(outcomes),
        metrics=compute(outcomes),
    )


def evaluate_synthetic(
    folder: Path,
    read_file: ReadFile | None = None,
    *,
    allow_cloud_model: bool = False,
    max_cost_usd: Decimal = Decimal(0),
    set_name: str | None = None,
    date: str | None = None,
) -> EvalResult:
    """Every file of a `billx synth` folder (clean, scans, photos, non-bills and planted
    misreads) through the engine."""
    folder = Path(folder)
    return run(
        load_synthetic(folder),
        read_file,
        allow_cloud_model=allow_cloud_model,
        max_cost_usd=max_cost_usd,
        set_name=set_name or synthetic_set_name(folder),
        set_kind="synthetic",
        date=date,
    )


def evaluate_golden(
    read_file: ReadFile | None = None,
    *,
    allow_cloud_model: bool = False,
    max_cost_usd: Decimal = Decimal(0),
    manifest: Path | None = None,
    root: Path | None = None,
    set_name: str = "golden",
    date: str | None = None,
) -> EvalResult:
    """The confirmed real bills of the golden manifest (the studio's, under BILLX_DATA_DIR,
    unless `manifest` is given); a person runs this (section 10). The report says
    `unmeasured`."""
    if manifest is None:
        from billx.platform.studio.golden import manifest_path

        manifest = manifest_path()
    return run(
        load_golden(Path(manifest), root),
        read_file,
        allow_cloud_model=allow_cloud_model,
        max_cost_usd=max_cost_usd,
        set_name=set_name,
        set_kind="golden",
        date=date,
    )


__all__ = [
    "CaseResult",
    "EvalResult",
    "ReadFile",
    "evaluate_golden",
    "evaluate_synthetic",
    "run",
    "run_case",
    "write_report",
]
