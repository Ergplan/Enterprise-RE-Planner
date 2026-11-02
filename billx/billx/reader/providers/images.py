"""Page images as the models receive them: downscaled to `max_image_edge_px` (rule 12: the
limit is configuration), and for Model B cut into three overlapping horizontal bands (5.1).

Nothing here reads a value; it only resizes and crops pixels with Pillow. A band is a crop
of the page sent beside the whole page so small print is legible; it is never a region found
by another reader (that would break independence).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from billx.reader.providers.base import Page

#: Each of the three bands is a third of the page's height, extended into each neighbour so
#: that adjacent bands overlap by this fraction of a band's height (a line cut by one band
#: edge is whole in the next band).
BAND_OVERLAP = 0.15
BAND_COUNT = 3

_FORMAT = {"image/png": "PNG", "image/jpeg": "JPEG"}


@dataclass(frozen=True)
class Band:
    page_index: int
    position: str  # top | middle | bottom
    page: Page


def _open(page: Page) -> Image.Image:
    """The decoded page; ValueError (no value in it) when the bytes are not an image."""
    try:
        img = Image.open(io.BytesIO(page.data))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("page is not a decodable image") from e
    return img


def _encode(img: Image.Image, mime: str) -> Page:
    fmt = _FORMAT.get(mime, "PNG")
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return Page("image/jpeg" if fmt == "JPEG" else "image/png", buf.getvalue())


def downscale(page: Page, max_edge_px: int) -> Page:
    """The page unchanged when its longest side is within `max_edge_px`, else resized so the
    longest side equals it (aspect kept, LANCZOS). The mime type is kept. A page that
    cannot be decoded is sent as it is (the model, not this code, reports it)."""
    try:
        img = _open(page)
    except ValueError:
        return page
    w, h = img.size
    if max(w, h) <= max_edge_px:
        return page
    scale = max_edge_px / max(w, h)
    resized = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return _encode(resized, page.mime)


def band_boxes(
    height: int, count: int = BAND_COUNT, overlap: float = BAND_OVERLAP
) -> list[tuple[int, int]]:
    """(top, bottom) pixel rows of `count` horizontal bands over `height` rows: equal thirds,
    each extended by half the overlap into its neighbours, clipped to the page."""
    band = height / count
    ext = band * overlap / 2
    boxes = []
    for i in range(count):
        top = max(0, round(i * band - ext))
        bottom = min(height, round((i + 1) * band + ext))
        boxes.append((top, bottom))
    return boxes


def bands(page: Page, page_index: int) -> list[Band]:
    """The page's three bands (top, middle, bottom) as pages of the same mime type.
    ValueError when the page cannot be decoded."""
    img = _open(page)
    w, h = img.size
    names = ("top", "middle", "bottom")
    out = []
    for name, (top, bottom) in zip(names, band_boxes(h), strict=True):
        crop = img.crop((0, top, w, bottom))
        out.append(Band(page_index, name, _encode(crop, page.mime)))
    return out
