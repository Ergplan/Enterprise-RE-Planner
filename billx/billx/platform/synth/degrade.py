"""Scans (image-only PDF, no text layer) and photo-like JPEGs made from a digital PDF's pages."""

import time

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter

PHOTO_VARIANTS = ("rotation", "perspective", "blur", "glare", "lowres")
TABLE = (96, 78, 60)  # the desk the "photo" was taken on


def render(pdf_path, dpi: int = 150) -> list[Image.Image]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return [page.render(scale=dpi / 72).to_pil().convert("RGB") for page in pdf]
    finally:
        pdf.close()


def _noise(img: Image.Image, rng, sigma: float) -> Image.Image:
    a = np.asarray(img, dtype=np.int16)
    a = a + rng.normal(0, sigma, a.shape).astype(np.int16)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def scan(pdf_path, out_path, seed: int) -> None:
    """Grey page, skew under 1.5 degrees, sensor noise; saved as image-only PDF."""
    rng = np.random.default_rng(seed)
    pages = []
    for img in render(pdf_path):
        g = img.convert("L").rotate(float(rng.uniform(-1.5, 1.5)), Image.BICUBIC, fillcolor=255)
        pages.append(_noise(g, rng, 10))
    fixed = time.gmtime(1767225600)  # 2026-01-01Z; Pillow would stamp the clock otherwise
    pages[0].save(
        out_path,
        "PDF",
        resolution=150,
        save_all=True,
        append_images=pages[1:],
        title="Synthetic scan",
        creationDate=fixed,
        modDate=fixed,
    )


def _perspective(img: Image.Image, rng) -> Image.Image:
    """Page on the desk, shot at an angle: corners pulled in by up to 9%."""
    pad = 80
    w, h = img.size
    canvas = Image.new("RGB", (w + 2 * pad, h + 2 * pad), TABLE)
    canvas.paste(img, (pad, pad))
    cw, ch = canvas.size

    def j(n):
        return float(rng.uniform(0, 0.09 * n))

    dst = [(j(cw), j(ch)), (cw - j(cw), j(ch)), (cw - j(cw), ch - j(ch)), (j(cw), ch - j(ch))]
    src = [(0, 0), (cw, 0), (cw, ch), (0, ch)]
    a, b = [], []
    for (x, y), (u, v) in zip(dst, src, strict=True):
        a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        b += [u, v]
    coeffs = np.linalg.solve(np.array(a), np.array(b)).tolist()
    return canvas.transform(canvas.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=TABLE)


def _glare(img: Image.Image, rng) -> Image.Image:
    """A soft bright ellipse, as from a ceiling light, over part of the page."""
    w, h = img.size
    cx, cy = float(rng.uniform(0.25, 0.75)) * w, float(rng.uniform(0.25, 0.75)) * h
    rx, ry = 0.22 * w, 0.12 * h
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=215)
    mask = mask.filter(ImageFilter.GaussianBlur(60))
    return Image.composite(Image.new("RGB", img.size, (255, 255, 250)), img, mask)


def photo(pdf_path, out_path, variant: str, seed: int) -> None:
    """One named photo-like variant of page 1, as a JPEG."""
    rng = np.random.default_rng(seed)
    img = render(pdf_path)[0]
    quality = 82
    if variant == "rotation":
        angle = float(rng.uniform(5, 12)) * (1 if rng.random() < 0.5 else -1)
        img = img.rotate(angle, Image.BICUBIC, expand=True, fillcolor=TABLE)
    elif variant == "perspective":
        img = _perspective(img, rng)
    elif variant == "blur":
        img = img.filter(ImageFilter.GaussianBlur(float(rng.uniform(1.6, 2.4))))
    elif variant == "glare":
        img = _glare(img, rng)
    elif variant == "lowres":
        img = img.resize((img.width * 35 // 100, img.height * 35 // 100), Image.BILINEAR)
        quality = 60
    else:
        raise ValueError(f"unknown photo variant {variant!r}")
    tint = Image.new("RGB", img.size, (255, 236, 205))  # warm indoor light
    img = _noise(Image.blend(img, tint, 0.08), rng, 4)
    img.save(out_path, "JPEG", quality=quality)
