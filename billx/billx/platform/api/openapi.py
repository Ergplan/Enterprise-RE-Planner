"""`contract/openapi.json`, generated from the FastAPI app so it can never drift from the
code (build prompt Stage 2.4). The document describes the esgos-1.1 mode (the superset);
the 1.0 shapes are its subset as `contract/esgos-1.0/contract.md` writes them."""

from __future__ import annotations

import json
from pathlib import Path

from billx.core.schema import ENGINE_VERSION
from billx.platform.api.app import ApiSettings, create_app


def openapi_document() -> dict:
    app = create_app(
        ApiSettings(mode="esgos-1.1", token="x", data_dir=Path("/tmp/billx-openapi")),
        providers=lambda: (None, None),
        start_workers=False,
    )
    doc = app.openapi()
    doc["info"] = {
        "title": "billx bill engine",
        "version": ENGINE_VERSION,
        "description": "esgOS bill engine contract 1.0 with the 1.1 additions. "
        "See contract/esgos-1.0/contract.md and contract/esgos-1.1/contract.md.",
    }
    return doc


def write_openapi(out: Path, *, check: bool = False) -> bool:
    """Write the document; with `check`, only report whether the file is stale (True)."""
    text = json.dumps(openapi_document(), indent=1, sort_keys=True) + "\n"
    current = out.read_text(encoding="utf-8") if out.is_file() else None
    changed = current != text
    if not check and changed:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return changed
