"""Stage 0 local-OCR check (section 3.1): can PaddleOCR read a synthetic bill here?

Renders a synthetic bill line with known text, reads it with PaddleOCR and, if that
fails, with RapidOCR (PaddleOCR's models on ONNX Runtime). Prints one JSON line:
{"platform": ..., "reader": "paddleocr" | "rapidocr" | "none", "found": [...], "error": ...}
"""

from __future__ import annotations

import json
import platform
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EXPECTED = ["SYNTHETIC", "12345.67", "kWh"]


def synthetic_page(path: Path) -> None:
    img = Image.new("RGB", (1400, 260), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 56)
    except OSError:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 56)
        except OSError:
            font = ImageFont.load_default(size=56)
    draw.text((40, 40), "SYNTHETIC TEST BILL", fill="black", font=font)
    draw.text((40, 140), "Units consumed 12345.67 kWh", fill="black", font=font)
    img.save(path)


def read_paddle(path: Path) -> str:
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(lang="en", use_textline_orientation=False)
    out = ocr.predict(str(path))
    return " ".join(t for page in out for t in page["rec_texts"])


def read_rapid(path: Path) -> str:
    from rapidocr import RapidOCR

    result = RapidOCR()(str(path))
    return " ".join(result.txts or [])


def main() -> int:
    plat = f"{'macos' if sys.platform == 'darwin' else 'linux'}-{platform.machine().lower()}"
    plat = plat.replace("aarch64", "arm64").replace("x86_64", "amd64")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "synthetic.png"
        synthetic_page(page)
        errors = {}
        for name, reader in (("paddleocr", read_paddle), ("rapidocr", read_rapid)):
            try:
                text = reader(page)
            except Exception as exc:
                errors[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
                continue
            found = [w for w in EXPECTED if w.lower() in text.lower()]
            if len(found) == len(EXPECTED):
                print(
                    json.dumps({"platform": plat, "reader": name, "found": found, "errors": errors})
                )
                return 0
            errors[name] = f"read only {found}"
    print(json.dumps({"platform": plat, "reader": "none", "found": [], "errors": errors}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
