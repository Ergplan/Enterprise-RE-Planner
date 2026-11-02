"""Evaluation cases from a set with truth: the synthetic manifest (`billx synth`) or the
golden manifest (the studio's confirmations in `~/billx-data/golden/manifest.jsonl`).

One `EvalCase` per file: where it is, what it is (document type, layout, input kind), its
truth on the contract's field paths, and the planted record when it is a planted misread.
A golden case is named by a sha256 prefix, never by its file name or a value (rule 10).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

BILL_TYPES = ("electricity_bill", "gas_bill")
FIELD_KIND = {"electricity_bill": "electricity", "gas_bill": "gas"}
NOT_PRINTED = "not_printed"  # the studio's marker for a field the page does not print
_INPUT_KINDS = {"scan": "scan_pdf", "photo": "photo_jpeg"}  # the studio's names -> synth's
SetKind = Literal["synthetic", "golden"]


def _no_float(s: str):
    raise ValueError(f"float in a truth file: {s}")


def load_json(path: Path):
    """JSON with every number kept exact (a float literal is an error)."""
    return json.loads(path.read_text(encoding="utf-8"), parse_float=_no_float)


@dataclass(frozen=True)
class Planted:
    """What a planted-misread file carries: the check that must fail and where the planted
    string sits (a contract path, or a `tod.`/`charges[]` path of the truth file)."""

    check: str
    path: str
    kind: str


@dataclass(frozen=True)
class EvalCase:
    id: str
    path: Path
    document_type: str
    layout: str
    input_kind: str
    truth: dict[str, str | None]
    planted: Planted | None = None
    sha256: str | None = None
    set_kind: SetKind = "synthetic"

    @property
    def is_bill(self) -> bool:
        return self.document_type in BILL_TYPES

    @property
    def field_kind(self) -> str | None:
        return FIELD_KIND.get(self.document_type)


def load_synthetic(folder: Path) -> list[EvalCase]:
    """Every file of a `billx synth` output folder, from its manifest and truth files."""
    folder = Path(folder)
    manifest = load_json(folder / "manifest.json")
    cases = []
    for entry in manifest["files"]:
        truth = load_json(folder / entry["truth"])
        planted = None
        if entry.get("planted"):
            p = truth["planted"]
            planted = Planted(check=p["check"], path=p["path"], kind=p["kind"])
        cases.append(
            EvalCase(
                id=entry["file"],
                path=folder / entry["file"],
                document_type=truth["document_type"],
                layout=truth["layout"],
                input_kind=truth["input_kind"],
                truth=dict(truth.get("fields", {})),
                planted=planted,
                sha256=entry.get("sha256"),
                set_kind="synthetic",
            )
        )
    return cases


def synthetic_set_name(folder: Path) -> str:
    manifest = load_json(Path(folder) / "manifest.json")
    return f"synthetic-seed-{manifest.get('seed', 'unknown')}"


def load_golden(manifest: Path, root: Path | None = None) -> list[EvalCase]:
    """The latest confirmation per bill from the studio's append-only manifest. `root`
    resolves relative `source_path`s. Fields the person marked not printed become None."""
    latest: dict[str, dict] = {}
    for line in Path(manifest).read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line, parse_float=_no_float)
            latest[entry["sha256"]] = entry
    cases = []
    for sha, entry in latest.items():
        source = Path(entry["source_path"])
        if root is not None and not source.is_absolute():
            source = Path(root) / source
        kind = entry.get("bill_kind", "electricity")
        fields = {
            path: (None if value == NOT_PRINTED else value)
            for path, value in entry.get("fields", {}).items()
        }
        cases.append(
            EvalCase(
                id=sha[:12],
                path=source,
                document_type=f"{kind}_bill",
                layout=entry.get("layout_id") or entry.get("discom") or "unknown",
                input_kind=_INPUT_KINDS.get(entry.get("input_kind"), entry.get("input_kind")),
                truth=fields,
                sha256=sha,
                set_kind="golden",
            )
        )
    return cases
