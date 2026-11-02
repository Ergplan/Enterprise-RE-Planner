"""Shared helpers for the reader tests: the synthetic set of seed 1 and its truth files."""

import json
from pathlib import Path

from billx.platform.synth.cli import build


def build_set(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("synth")
    build(out, 1)
    return out


def entries(
    out: Path,
    input_kind: str | None = None,
    document_type: str | None = None,
    planted: bool = False,
) -> list:
    """Manifest entries, clean bills only unless `planted` is asked for."""
    files = json.loads((out / "manifest.json").read_text())["files"]
    return [
        e
        for e in files
        if (input_kind is None or e["input_kind"] == input_kind)
        and (document_type is None or e["document_type"] == document_type)
        and bool(e.get("planted")) == planted
    ]


def truth(out: Path, entry: dict) -> dict:
    return json.loads((out / entry["truth"]).read_text())
