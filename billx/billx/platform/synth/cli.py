"""`billx synth`: synthetic bills and other documents with known values, a truth file beside each.

Same seed, same values and same digital-PDF text. Output: <out>/<file>, <out>/<stem>.truth.json
for every file, and <out>/manifest.json listing them all. With `--planted` (the default) every
clean electricity and gas bill also gets its planted-misread variants
(<base>.planted-<check>.pdf, `planted: true` in the manifest) and every clean electricity
bill a reader-misread fixture (<base>.misreads.json, named by the manifest entry's
`misreads`).
"""

import hashlib
import json
import random
import time
import zlib
from decimal import Decimal
from pathlib import Path

from billx.platform.synth import degrade, documents, electricity, planted, values

BILLS_PER_LAYOUT = 2
ELECTRICITY = {
    "avvnl-ht-synth-v1": (values.avvnl, electricity.avvnl_pdf),
    "pvvnl-hv2-synth-v1": (values.pvvnl, electricity.pvvnl_pdf),
}
# (name, values generator, renderer, photo variant made from it)
OTHERS = [
    ("gas-citygas-synth-v1", lambda r: values.gas(r, "a"), documents.gas_pdf, "rotation"),
    ("gas-gridsales-synth-v1", lambda r: values.gas(r, "b"), documents.gas_pdf, "perspective"),
    ("water-municipal-synth-v1", values.water, documents.water_pdf, "blur"),
    ("telecom-fictional-synth-v1", values.telecom, documents.telecom_pdf, "glare"),
    ("receipt-store-synth-v1", values.receipt, documents.receipt_pdf, "rotation"),
    ("invoice-supplies-synth-v1", values.invoice, documents.invoice_pdf, "lowres"),
    ("letter-synth-v1", values.letter, documents.letter_pdf, "perspective"),
]


def _json(obj) -> str:
    def default(o):
        if isinstance(o, Decimal):
            return str(o)
        raise TypeError(f"not JSON-safe: {type(o).__name__}")

    return json.dumps(obj, indent=2, ensure_ascii=False, default=default) + "\n"


def _seed(seed: int, name: str) -> int:
    return zlib.crc32(f"{seed}:{name}".encode())


def _emit(
    out: Path, doc: dict, seed: int, name: str, kind: str, variant: str, source, plant=None
) -> dict:
    """Write the truth sidecar for `name` and return its manifest entry. `plant` is the
    planted record of a planted variant; the truth keeps the clean bill's values beside it."""
    sidecar = name.rsplit(".", 1)[0] + ".truth.json"
    truth = {k: v for k, v in doc.items() if k != "values"}
    body = {
        "truth_version": "1",
        "generator": "billx synth",
        "seed": seed,
        "file": name,
        "input_kind": kind,
        "variant": variant,
        "derived_from": source,
        **truth,
    }
    if plant is not None:
        body["planted"] = plant
    (out / sidecar).write_text(_json(body))
    entry = {
        "file": name,
        "truth": sidecar,
        "document_type": doc["document_type"],
        "layout": doc["layout"],
        "input_kind": kind,
        "variant": variant,
        "planted": plant is not None,
        "sha256": hashlib.sha256((out / name).read_bytes()).hexdigest(),
    }
    if plant is not None:
        entry["check"] = plant["check"]
    return entry


def _planted(out: Path, seed: int, bill: dict, base: str, render, digital: str) -> list:
    """Render every planted variant of a clean bill from an altered copy; the truth beside
    each is the clean bill's plus the `planted` record."""
    entries = []
    for check, altered, record in planted.variants(bill):
        name = f"{base}.planted-{check}.pdf"
        render(altered, out / name)
        entries.append(
            _emit(out, bill, seed, name, "digital_pdf", f"planted-{check}", digital, record)
        )
    return entries


def _misreads(out: Path, seed: int, bill: dict, base: str, entry: dict) -> None:
    """Write <base>.misreads.json for a clean electricity bill and name it in its entry."""
    name = f"{base}.misreads.json"
    rng = random.Random(f"{seed}:{base}:misreads")
    body = {
        "generator": "billx synth",
        "seed": seed,
        "file": entry["file"],
        "truth": entry["truth"],
        "misreads": planted.misreads(bill, rng),
    }
    (out / name).write_text(_json(body))
    entry["misreads"] = name


def _files(out: Path, seed: int, doc: dict, base: str, render, scan: bool, variants) -> list:
    digital = f"{base}.digital.pdf"
    render(doc, out / digital)
    entries = [_emit(out, doc, seed, digital, "digital_pdf", "clean", None)]
    if scan:
        name = f"{base}.scan.pdf"
        degrade.scan(out / digital, out / name, _seed(seed, name))
        entries.append(_emit(out, doc, seed, name, "scan_pdf", "scan", digital))
    for variant in variants:
        name = f"{base}.photo-{variant}.jpg"
        degrade.photo(out / digital, out / name, variant, _seed(seed, name))
        entries.append(_emit(out, doc, seed, name, "photo_jpeg", variant, digital))
    return entries


def build(out: Path, seed: int, with_planted: bool = True) -> list[dict]:
    """Write every synthetic file under `out`; return the manifest entries. With
    `with_planted`, the planted variants and misread fixtures come too."""
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for layout, (gen, render) in ELECTRICITY.items():
        for n in range(1, BILLS_PER_LAYOUT + 1):
            base = f"{layout}_{n:02d}"
            bill = gen(random.Random(f"{seed}:{base}"), n)
            clean = _files(out, seed, bill, base, render, True, degrade.PHOTO_VARIANTS)
            if with_planted:
                _misreads(out, seed, bill, base, clean[0])
                clean += _planted(out, seed, bill, base, render, clean[0]["file"])
            entries += clean
    for base, gen, render, variant in OTHERS:
        doc = gen(random.Random(f"{seed}:{base}"))
        clean = _files(out, seed, doc, base, render, False, [variant])
        if with_planted:
            clean += _planted(out, seed, doc, base, render, clean[0]["file"])
        entries += clean
    manifest = {"generator": "billx synth", "seed": seed, "files": entries}
    (out / "manifest.json").write_text(_json(manifest))
    return entries


def run(args) -> int:
    started = time.monotonic()
    entries = build(Path(args.out), args.seed, getattr(args, "planted", True))
    n_planted = sum(1 for e in entries if e["planted"])
    print(
        f"billx synth: {len(entries)} files ({n_planted} planted; + truth sidecars, misread "
        f"fixtures, manifest.json) in {args.out} from seed {args.seed}, "
        f"{time.monotonic() - started:.1f}s"
    )
    return 0
