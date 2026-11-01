"""Register the regulation corpus: the PDFs listed in packages/rulebooks/corpus/tariff-library.json
(the index kept beside the Mac mini's tariff-order folders), each with its regulator URL and the
page ranges its notes name ("Annexure-I, PDF pages 352-400").

Usage: python -m ergplan.documents.corpus --root data/corpus/India_DISCOM_Tariff_Orders_Final_2026
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..core.settings import get_settings
from ..db.base import session_scope
from . import service

_RANGE = re.compile(r"PDF pages (\d+)\s*[-–]\s*(\d+)", re.I)
_SCHEDULE_WORDS = re.compile(r"schedule|annexure", re.I)


@dataclass(frozen=True)
class CorpusEntry:
    path: str
    state: str | None
    commission: str | None
    title: str
    order_type: str | None
    order_date: date | None
    utilities: tuple[str, ...]
    provenance_url: str | None
    notes: tuple[str, ...]
    kind: str

    @property
    def page_hints(self) -> dict[str, list[int]]:
        """Named page ranges taken from the notes; the first schedule-like range is `schedule`."""
        hints: dict[str, list[int]] = {}
        for note in self.notes:
            for m in _RANGE.finditer(note):
                lo, hi = int(m.group(1)), int(m.group(2))
                label = note[: m.start()].strip(" :,.;").split(":")[0].strip() or "section"
                key = (
                    "schedule" if _SCHEDULE_WORDS.search(label) and "schedule" not in hints else _slug(label)
                )
                hints.setdefault(key, [lo, hi])
        return hints


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:40] or "section"


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def load_index(path: Path | None = None) -> list[CorpusEntry]:
    data = json.loads((path or get_settings().corpus_index).read_text())
    out = []
    for e in data["entries"]:
        out.append(
            CorpusEntry(
                path=e["path"],
                state=e.get("state"),
                commission=e.get("commission"),
                title=e.get("title") or Path(e["path"]).stem,
                order_type=e.get("order_type"),
                order_date=_date(e.get("order_date")),
                utilities=tuple(e.get("utilities") or ()),
                provenance_url=e.get("provenance_url"),
                notes=tuple(e.get("notes") or ()),
                kind=e.get("kind") or "order",
            )
        )
    return out


def register_corpus(root: Path, actor: str = "corpus-loader", index: Path | None = None) -> dict[str, Any]:
    """Register every indexed PDF found under root. Missing files are reported, never invented."""
    registered: list[dict[str, str]] = []
    existing: list[dict[str, str]] = []
    missing: list[str] = []
    for entry in load_index(index):
        f = root / entry.path
        if not f.exists():
            missing.append(entry.path)
            continue
        meta = service.DocumentMeta(
            title=entry.title,
            regulator=entry.commission,
            jurisdiction=entry.state,
            document_kind=entry.kind if entry.kind in {"order", "regulation"} else "supporting",
            utilities=entry.utilities,
            order_date=entry.order_date,
            url_public=entry.provenance_url,
            notes=entry.notes,
            page_hints=entry.page_hints,
            original_filename=f.name,
        )
        with session_scope(actor=actor) as s:
            doc, created = service.register(s, f.read_bytes(), meta, uploaded_by=actor)
            (registered if created else existing).append({"id": doc.id, "path": entry.path})
    return {"registered": registered, "existing": existing, "missing": missing}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--index", type=Path, default=None)
    args = ap.parse_args()
    result: dict[str, Any] = register_corpus(args.root, index=args.index)
    print(json.dumps({k: len(v) for k, v in result.items()}), "missing:", *result["missing"], sep="\n  ")


if __name__ == "__main__":
    main()
