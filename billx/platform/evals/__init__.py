"""`billx eval` (build prompt section 8): the engine over a set with truth, with the metrics
per layout, input kind and route, and a report with no values in it.

Public API:

- `evaluate_synthetic(folder, read_file=None, *, allow_cloud_model, max_cost_usd)`: every
  file of a `billx synth` folder (clean, scans, photos, non-bills and planted misreads).
- `evaluate_golden(read_file=None, *, allow_cloud_model, max_cost_usd, manifest=None)`:
  the studio's confirmed bills; the report is labelled `unmeasured`.
- `run(cases, read_file=None, *, allow_cloud_model, max_cost_usd)`: the runner itself.
- `write_report(result, path)`: the Markdown report and the JSON summary beside it.
- `EvalResult.summary()`, `.markdown()`, `.ok()`: the JSON summary, the report text, and
  whether the set meets section 10 (no silent error, no false refusal, every planted
  misread caught).

`read_file` is the engine's `billx.reader.pipeline.read_file`, imported lazily when None;
tests inject a fake.
"""

from billx.platform.evals.manifest import (
    EvalCase,
    Planted,
    load_golden,
    load_synthetic,
    synthetic_set_name,
)
from billx.platform.evals.metrics import GroupMetrics, Metrics, Outcome, rule_of_three
from billx.platform.evals.report import render_markdown, summary, write_report
from billx.platform.evals.runner import (
    CaseResult,
    EvalResult,
    ReadFile,
    evaluate_golden,
    evaluate_synthetic,
    run,
)

__all__ = [
    "CaseResult",
    "EvalCase",
    "EvalResult",
    "GroupMetrics",
    "Metrics",
    "Outcome",
    "Planted",
    "ReadFile",
    "evaluate_golden",
    "evaluate_synthetic",
    "load_golden",
    "load_synthetic",
    "render_markdown",
    "rule_of_three",
    "run",
    "summary",
    "synthetic_set_name",
    "write_report",
]
