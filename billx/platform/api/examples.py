"""`contract/examples/<mode>/`: synthetic requests and responses, at least one per route and
one per failure, for both modes (build prompt Stage 2.4; contract 1.0 section 9). Products
build their contract tests and mocks on them. Real bills are never in examples.

Each example is a folder: `request.json` (the options and the synthetic file's name, which
`billx synth --seed 1` regenerates byte for byte), the file itself, and `response.json`
(the rendered result with `seconds` and `engine_version` left as they were produced; a
contract test compares everything but timings).

Proof rule 2 means no bill passes without a model reading, so the passed examples replay
one: `ReplayModel` answers from the synthetic file's own truth file (copied into the example
folder), as a correct model would. `request.json` says so (`"models": "replay"`), and no
example ever calls a real model.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from billx.core.schema import UsageRecord
from billx.platform.api.render import render_envelope, render_text
from billx.reader.read.consensus import RawRead, ReaderOutput

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "contract" / "examples"
MODES = ("esgos-1.0", "esgos-1.1")


@dataclass(frozen=True)
class Case:
    name: str  # folder name: what the example shows
    file: str  # a file name in the synthetic set
    kind: str = "bill"
    allow_cloud_model: bool = False
    replay: bool = False  # the models are ReplayModels over the file's truth
    note: str = ""


def truth_path(file: Path) -> Path:
    return file.with_suffix(".truth.json")


def printed(truth: dict) -> dict:
    """What the file prints: the truth's printed values with a planted change applied."""
    out = dict(truth["printed"])
    planted = truth.get("planted")
    if planted and planted.get("planted_printed"):
        out[planted["path"]] = planted["planted_printed"]
    return out


class ReplayModel:
    """A model reader that transcribes a synthetic file's truth: what a correct model would
    return. Keyed by the file's sha (the engine's `bill_id`); an unknown file reads nothing."""

    def __init__(self, reader_name: str, family: str, truths: dict[str, dict]):
        self.reader_name, self.family, self.truths = reader_name, family, truths
        self.calls = 0

    @classmethod
    def pair(cls, files) -> tuple[ReplayModel, ReplayModel]:
        truths = {
            hashlib.sha256(f.read_bytes()).hexdigest(): json.loads(truth_path(f).read_text())
            for f in files
        }
        return cls("model_a", "openai", truths), cls("model_b", "anthropic", truths)

    def _reading(self, bill_id: str, fields: list[str]):
        t = self.truths.get(bill_id)
        if t is None:
            outputs = ReaderOutput(
                self.reader_name,
                "vision",
                family=self.family,
                model_id="replay",
                prompt_version="replay",
                fields={},
            )
        else:
            text = printed(t)
            outputs = ReaderOutput(
                self.reader_name,
                "vision",
                family=self.family,
                model_id="replay",
                prompt_version="replay",
                fields={p: RawRead(text[p]) for p in fields if p in text},
                meters=[
                    {
                        "register": reg,
                        "tod_slot": r["slot"],
                        **{k: r["printed"][k] for k in ("present", "past", "difference")},
                        "multiplying_factor": r["printed"]["mf"],
                        "consumption": r["printed"]["consumption"],
                    }
                    for reg in ("kWh", "kVAh")
                    for r in t["tod"][reg.lower()] + [t["tod"][reg.lower() + "_total"]]
                ],
                lines=[
                    {
                        "label": x["label"],
                        "quantity": x["printed"]["quantity"],
                        "rate": x["printed"]["rate"],
                        "amount": x["printed"]["amount"],
                        "unit": x["unit"],
                        "kind": "item",
                        "stage": "current",
                    }
                    for x in t["charges"]
                ]
                + [
                    {
                        "label": "Current Charges (A)",
                        "amount": text["totals.current_charges"],
                        "kind": "subtotal",
                    },
                    {"label": "Arrears (B)", "amount": text["totals.arrears"], "kind": "subtotal"},
                    {
                        "label": "Net Payable (A+B)",
                        "amount": text["totals.net_payable"],
                        "kind": "subtotal",
                    },
                ],
            )
        usage = [
            UsageRecord(
                provider=self.family,
                model=f"{self.family}:replay",
                purpose="bill_read",
                input_tokens=10,
                output_tokens=5,
                cost_usd=Decimal("0.01"),
            )
        ]

        class _Result:
            pass

        r = _Result()
        r.usage = usage
        r.to_output = lambda: outputs
        self.calls += 1
        return r

    def read_bill(self, pages, *, bill_kind, fields, bill_id, max_cost_usd, hints=()):
        return self._reading(bill_id, [f["path"] for f in fields])

    def read_fields(self, pages, *, bill_kind, fields, bill_id, max_cost_usd, hints=()):
        return self._reading(bill_id, [f["path"] for f in fields])


CASES = (
    Case(
        "route-cloud-model-passed",
        "avvnl-ht-synth-v1_01.digital.pdf",
        allow_cloud_model=True,
        replay=True,
        note="a digital PDF verified by the text layer and one model family agreeing (replayed)",
    ),
    Case(
        "route-cloud-model-passed-pvvnl",
        "pvvnl-hv2-synth-v1_01.digital.pdf",
        allow_cloud_model=True,
        replay=True,
        note="the second synthetic layout",
    ),
    Case(
        "printed-inconsistency",
        "avvnl-ht-synth-v1_01.planted-G09.pdf",
        allow_cloud_model=True,
        replay=True,
        note="the bill's own numbers don't add up: 1.1 passes with a flag, 1.0 fails with a note",
    ),
    Case(
        "digital-without-a-model",
        "avvnl-ht-synth-v1_01.digital.pdf",
        note="a digital PDF with allow_cloud_model false: refused (proof rule 2), with its "
        "reading and checks",
    ),
    Case(
        "model-not-allowed",
        "avvnl-ht-synth-v1_01.scan.pdf",
        note="a scan with allow_cloud_model false: refused, never passed on one reading",
    ),
    Case(
        "no-model-configured",
        "avvnl-ht-synth-v1_01.scan.pdf",
        allow_cloud_model=True,
        note="a scan with cloud allowed but no key configured: unreadable (no_model_configured)",
    ),
    Case("not-a-bill", "letter-synth-v1.digital.pdf", note="a letter: not_a_bill"),
    Case(
        "wrong-document-type",
        "water-municipal-synth-v1.digital.pdf",
        note="a water bill: not_a_bill with the type named in the note",
    ),
    Case("gas-bill", "gas-citygas-synth-v1.digital.pdf", note="a gas bill read generically"),
    Case(
        "kind-text", "pvvnl-hv2-synth-v1_01.digital.pdf", kind="text", note="pages and words only"
    ),
)


def write_examples(
    synth_dir: Path, out: Path = EXAMPLES, read_file=None, read_text_file=None
) -> list[Path]:
    """Run every case through the engine and write both modes' examples."""
    from billx.reader.pipeline import read_file as _read
    from billx.reader.pipeline import read_text_file as _text

    read_file = read_file or _read
    read_text_file = read_text_file or _text
    written = []
    for mode in MODES:
        for case in CASES:
            folder = out / mode / case.name
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir(parents=True)
            src = synth_dir / case.file
            shutil.copy(src, folder / case.file)
            if case.replay:
                shutil.copy(truth_path(src), truth_path(folder / case.file))
            options = {
                "request_id": f"example-{case.name}",
                "product": "esgos",
                "kind": case.kind,
                "allow_cloud_model": case.allow_cloud_model,
            }
            if case.allow_cloud_model:
                options["max_cost_usd"] = "1.00"
            request = {"file": case.file, "options": options, "note": case.note}
            if case.replay:
                request["models"] = "replay"
            (folder / "request.json").write_text(json.dumps(request, indent=1) + "\n")
            if case.kind == "text":
                rendered = render_text(read_text_file(src), mode)
            else:
                model_a, model_b = ReplayModel.pair([src]) if case.replay else (None, None)
                env = read_file(
                    src,
                    allow_cloud_model=case.allow_cloud_model,
                    max_cost_usd=Decimal(options.get("max_cost_usd", "0")),
                    contract="1.0" if mode == "esgos-1.0" else "1.1",
                    model_a=model_a,
                    model_b=model_b,
                )
                rendered = render_envelope(env, mode)
            (folder / "response.json").write_text(
                json.dumps(rendered, indent=1, ensure_ascii=False) + "\n"
            )
            written.append(folder)
    index = {
        "note": "Synthetic examples from billx synth --seed 1; one per route and per failure.",
        "cases": [
            {"name": c.name, "file": c.file, "kind": c.kind, "replay": c.replay, "note": c.note}
            for c in CASES
        ],
    }
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return written


VOLATILE = ("seconds", "engine_version")


def strip_volatile(obj):
    """A response without the fields that legitimately differ between runs."""
    if isinstance(obj, dict):
        return {k: strip_volatile(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [strip_volatile(v) for v in obj]
    return obj
