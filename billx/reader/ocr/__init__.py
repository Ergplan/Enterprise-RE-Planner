"""Local OCR (build prompt 5.1, reader `local_ocr`): words with boxes and confidences from a
rendered page, read by PaddleOCR, or by RapidOCR when PaddleOCR cannot be imported or
initialised (the linux/amd64 image). The engine is imported inside the functions and built
once, so importing this module never loads an OCR runtime.

The engines return one box per printed text line; `split_phrase` turns each into words with
boxes apportioned by character count, so the label rule and the row rules see the same shape
as the text layer. Confidences are the engine's recognition scores as Decimal, four places.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import threading
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from PIL import Image

from billx.core.settings import data_dir
from billx.reader.read.words import PLACES, WordBox, detach_colons, frac, split_phrase

log = logging.getLogger(__name__)
_lock = threading.Lock()
_predict_lock = threading.Lock()  # one page at a time: the engine is CPU-bound and not thread-safe
_engine: tuple[str, Any] | None = None

CACHE_VERSION = "1"  # bump when the word splitting or the engine settings change
DEFAULT_THREADS = 4  # the OMP thread cap applied when BILLX_OCR_THREADS is set


def cache_dir() -> Path | None:
    """Where OCR results are cached by image hash: BILLX_OCR_CACHE, else
    <BILLX_DATA_DIR>/cache/ocr; "off" disables it. The same bytes always give the same words
    (invariant 6), so a cached result is the engine's own."""
    raw = os.environ.get("BILLX_OCR_CACHE")
    if raw == "off":
        return None
    return Path(raw).expanduser() if raw else data_dir() / "cache" / "ocr"


def cpu_threads() -> int:
    try:
        return max(1, int(os.environ.get("BILLX_OCR_THREADS", DEFAULT_THREADS)))
    except ValueError:
        return DEFAULT_THREADS


def available() -> bool:
    """True when an OCR engine can be imported (PaddleOCR or RapidOCR)."""
    for name in ("paddleocr", "rapidocr"):
        try:
            __import__(name)
            return True
        except Exception:  # noqa: BLE001 - a broken install is "not available"
            continue
    return False


def engine_name() -> str | None:
    """Which engine answered (`paddleocr` or `rapidocr`), None before the first read."""
    return _engine[0] if _engine else None


def _load_engine() -> tuple[str, Any]:
    global _engine
    with _lock:
        if _engine is None:
            _engine = _build_engine()
        return _engine


def _build_engine() -> tuple[str, Any]:
    """PaddleOCR (English, no orientation models) first; RapidOCR when it fails to import, to
    initialise, or to read a tiny probe page (on linux/amd64 PaddleOCR fails inside its
    oneDNN executor at predict time, not at init). BILLX_OCR_ENGINE=rapidocr|paddleocr
    forces one engine."""
    forced = os.environ.get("BILLX_OCR_ENGINE", "").strip().lower()
    if forced == "rapidocr":
        return _rapid()
    try:
        from paddleocr import PaddleOCR

        kwargs = dict(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        # `cpu_threads` is deliberately NOT passed: with it, PaddleOCR 3.7 on macOS arm64 ran
        # single-threaded and a page took 300 s instead of 25 s. The engine uses the cores it
        # finds; BILLX_OCR_THREADS caps them through OMP_NUM_THREADS when set.
        if os.environ.get("BILLX_OCR_THREADS"):
            os.environ.setdefault("OMP_NUM_THREADS", str(cpu_threads()))
        ocr = PaddleOCR(**kwargs)
        _probe(ocr)  # a predict-time failure (linux/amd64) falls back too
        log.info("ocr engine ready: paddleocr")
        return "paddleocr", ocr
    except Exception as e:  # noqa: BLE001 - any failure to import, init or read falls back
        if forced == "paddleocr":
            raise
        log.info("paddleocr unavailable (%s); trying rapidocr", type(e).__name__)
    return _rapid()


def _rapid() -> tuple[str, Any]:
    from rapidocr import RapidOCR

    ocr = RapidOCR()
    log.info("ocr engine ready: rapidocr")
    return "rapidocr", ocr


def _probe(ocr) -> None:
    """Read a tiny blank page so an engine that fails only at predict time fails here."""
    import numpy as np

    blank = np.full((64, 256, 3), 255, dtype=np.uint8)
    for _ in ocr.predict(blank):
        pass


def read_words(image: Image.Image, page: int = 0) -> list[WordBox]:
    """The words of a page image with boxes as fractions of the image and confidences. A
    page already read (same bytes, same engine) comes from the cache."""
    rgb = image.convert("RGB")
    _load_engine()  # the key names the engine, so load it before computing the key
    key = _cache_key(rgb)
    cached = _cache_get(key, page)
    if cached is not None:
        log.info("ocr page %d: %d words (cache)", page, len(cached))
        return cached
    words = _read_words(rgb, page)
    _cache_put(key, words)
    return words


def _cache_key(rgb: Image.Image) -> str:
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    name = _engine[0] if _engine else "unloaded"
    return hashlib.sha256(buf.getvalue() + f"|{CACHE_VERSION}|{name}".encode()).hexdigest()


def _cache_get(key: str, page: int) -> list[WordBox] | None:
    root = cache_dir()
    if root is None or not (root / f"{key}.json").is_file():
        return None
    try:
        rows = json.loads((root / f"{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return [
        WordBox(
            r["text"],
            page,
            Decimal(r["x0"]),
            Decimal(r["y0"]),
            Decimal(r["x1"]),
            Decimal(r["y1"]),
            Decimal(r["c"]) if r.get("c") is not None else None,
        )
        for r in rows
    ]


def _cache_put(key: str, words: list[WordBox]) -> None:
    root = cache_dir()
    if root is None:
        return
    try:
        root.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "text": w.text,
                "x0": str(w.x0),
                "y0": str(w.y0),
                "x1": str(w.x1),
                "y1": str(w.y1),
                "c": str(w.confidence) if w.confidence is not None else None,
            }
            for w in words
        ]
        tmp = root / f"{key}.tmp"
        tmp.write_text(json.dumps(rows), encoding="utf-8")
        tmp.replace(root / f"{key}.json")
    except OSError:
        log.info("ocr cache not writable")


def _read_words(rgb: Image.Image, page: int) -> list[WordBox]:
    """One page through the engine. Calls are serialised: several worker threads reading at
    once thrash the engine's threads (measured: four jobs finished one page in 15 minutes
    where one at a time takes 12 to 25 s) and PaddleOCR is not documented thread-safe. The
    rest of a job (rendering, the text layer, model calls, checks) still overlaps."""
    with _predict_lock:
        return _read_words_locked(rgb, page)


def _read_words_locked(rgb: Image.Image, page: int) -> list[WordBox]:
    import numpy as np

    name, ocr = _load_engine()
    array = np.asarray(rgb)
    if name == "paddleocr":
        phrases = _paddle_phrases(ocr, array)
    else:
        phrases = _rapid_phrases(ocr, array)
    words: list[WordBox] = []
    for text, score, poly in phrases:
        pts = np.asarray(poly, dtype=float).reshape(-1, 2)
        x0, y0 = frac(pts[:, 0].min(), rgb.width), frac(pts[:, 1].min(), rgb.height)
        x1, y1 = frac(pts[:, 0].max(), rgb.width), frac(pts[:, 1].max(), rgb.height)
        confidence = Decimal(str(float(score))).quantize(PLACES, ROUND_HALF_UP)
        words.extend(split_phrase(text, page, x0, y0, x1, y1, confidence))
    log.info("ocr page %d: %d words (%s)", page, len(words), name)
    return detach_colons(words)


def _paddle_phrases(ocr, array) -> list[tuple[str, float, Any]]:
    out = []
    for result in ocr.predict(array):
        texts = result.get("rec_texts") or []
        scores = result.get("rec_scores") or []
        polys = result.get("rec_polys")
        if polys is None:
            polys = result.get("dt_polys") or []
        out.extend(zip(texts, scores, polys, strict=False))
    return out


def _rapid_phrases(ocr, array) -> list[tuple[str, float, Any]]:
    result = ocr(array)
    if result is None or result.txts is None or result.boxes is None:
        return []
    scores = result.scores if result.scores is not None else [1.0] * len(result.txts)
    return list(zip(result.txts, scores, result.boxes, strict=False))
