"""Build-time OCR warm-up and runtime smoke check for the engine image (Stage 2.5).

Renders a tiny synthetic page (invented words, not a bill) and reads it through the engine's
own OCR path, `billx.reader.ocr.read_words`, so the engine choice and the models are exactly
the service's. It prints one JSON line:

    {"platform": "linux-arm64", "engine": "paddleocr" | "rapidocr", "words": 7}

At image build time this makes PaddleOCR download its models into PADDLE_PDX_CACHE_HOME
inside the image, so the running container needs no network (RapidOCR's models ship in its
wheel). Run it again in the finished container with `--network none` to prove that, and in
CI to record which engine each platform picks. Exit 1 when no engine reads the page.
"""

from __future__ import annotations

import json
import platform
import sys

from PIL import Image, ImageDraw, ImageFont

TEXT = "WARM UP 12345 kWh"  # invented words; nothing from a real bill


def synthetic_page() -> Image.Image:
    """A white page with one line of large black text, enough for any engine to find words."""
    img = Image.new("RGB", (900, 160), "white")
    ImageDraw.Draw(img).text((30, 40), TEXT, fill="black", font=ImageFont.load_default(size=56))
    return img


def platform_name() -> str:
    machine = platform.machine().lower().replace("aarch64", "arm64").replace("x86_64", "amd64")
    return f"{'macos' if sys.platform == 'darwin' else 'linux'}-{machine}"


def main() -> int:
    from billx.reader.ocr import engine_name, read_words

    try:
        words = read_words(synthetic_page())
    except Exception as exc:  # noqa: BLE001 - the build must say why no engine answered
        print(json.dumps({"platform": platform_name(), "engine": None, "error": repr(exc)[:300]}))
        return 1
    print(json.dumps({"platform": platform_name(), "engine": engine_name(), "words": len(words)}))
    return 0 if words else 1


if __name__ == "__main__":
    sys.exit(main())
