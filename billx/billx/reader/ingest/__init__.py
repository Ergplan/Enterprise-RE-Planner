"""Intake (build prompt 5.0): a file becomes a `Document` of rendered pages, each with its
genuine text-layer words when the PDF has one.

- PDF: pypdfium2 renders every page at 200 dpi. A page's text layer counts as genuine only
  when the page has visible text objects (render mode other than invisible or clip) and no
  image covers the page: a scanned page carrying a hidden OCR layer is never a text layer
  (5.1). A password-protected PDF raises `PasswordRequired`.
- JPG, PNG, WebP, TIFF (every frame is a page): Pillow, with the EXIF orientation applied.
  HEIC needs a decoder this build does not ship and raises `UnsupportedType`.
- Limits: `MAX_BYTES` and `MAX_PAGES` raise `TooLarge`.

Boxes are fractions of the page (Decimal, four places). Logs would carry only the sha256 and
counts; nothing here logs a value.
"""

from __future__ import annotations

import ctypes
import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as raw
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from billx.reader.read.words import WordBox, detach_colons, frac

MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 30
RENDER_DPI = 200
# An image whose bounds cover at least this share of the page area is a full-page image.
FULL_PAGE_COVER = 0.9
# Sub-pixel precision for text boxes: page coordinates are mapped to a device space this many
# times finer than the rendered bitmap.
BOX_SCALE = 16
INVISIBLE_RENDER_MODES = {
    raw.FPDF_TEXTRENDERMODE_INVISIBLE,
    raw.FPDF_TEXTRENDERMODE_CLIP,
}
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heic",
}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}


class IngestError(Exception):
    """Base of every intake error; the message never carries page content."""


class PasswordRequired(IngestError):
    """The PDF is encrypted and no password opened it."""


class TooLarge(IngestError):
    """The file exceeds MAX_BYTES or MAX_PAGES."""


class UnsupportedType(IngestError):
    """Not a PDF or a supported image, or an image format without a decoder (HEIC)."""


@dataclass
class Page:
    """One page: its rendered image, the image's pixel size, and the genuine text-layer words
    (None when the page has no genuine text layer; an empty list never occurs)."""

    index: int
    image: Image.Image
    width: int
    height: int
    text_words: list[WordBox] | None = None
    ocr_words: list[WordBox] | None = None  # filled by the local OCR reader on first use


@dataclass
class Document:
    sha256: str
    media_type: str
    pages: list[Page] = field(default_factory=list)
    # Docling's conversion of the whole file (DoclingDocument JSON), when Docling ran; a bill
    # of a multi-bill file shares it and reads its own pages from it
    docling: dict | None = None
    # the conversion while it runs (a Future): a bill joins it after its model readers have
    # started, so Docling and the model calls overlap
    docling_job: object | None = None

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def has_text_layer(self) -> bool:
        return any(p.text_words is not None for p in self.pages)


def sniff_media_type(data: bytes, hint: str | None = None) -> str | None:
    """The media type from the file's leading bytes, else the hint (a media type or a file
    name), else None."""
    head = data[:16]
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heif"):
        return "image/heic"
    if hint:
        if "/" in hint:
            return hint.lower()
        return MEDIA_TYPES.get(Path(hint).suffix.lower())
    return None


def load(
    source: Path | str | bytes,
    media_type: str | None = None,
    *,
    password: str | None = None,
    max_bytes: int = MAX_BYTES,
    max_pages: int = MAX_PAGES,
    dpi: int = RENDER_DPI,
) -> Document:
    """A Document from a path or the file's bytes. `media_type` is used only when the bytes do
    not identify themselves; for a path the suffix is the fallback hint."""
    if isinstance(source, bytes):
        data = source
    else:
        data = Path(source).read_bytes()
        media_type = media_type or Path(source).name
    if len(data) > max_bytes:
        raise TooLarge(f"file exceeds {max_bytes} bytes")
    kind = sniff_media_type(data, media_type)
    sha = hashlib.sha256(data).hexdigest()
    if kind == "application/pdf":
        pages = _pdf_pages(data, password, max_pages, dpi)
    elif kind in IMAGE_TYPES:
        pages = _image_pages(data, max_pages)
    elif kind == "image/heic":
        raise UnsupportedType("HEIC/HEIF needs a decoder this build does not include")
    else:
        raise UnsupportedType("not a PDF or a supported image (JPG, PNG, WebP, TIFF)")
    return Document(sha256=sha, media_type=kind, pages=pages)


# PDF ----------------------------------------------------------------------------------------


def _pdf_pages(data: bytes, password: str | None, max_pages: int, dpi: int) -> list[Page]:
    try:
        pdf = pdfium.PdfDocument(data, password=password)
    except pdfium.PdfiumError as e:
        if _is_password_error(e):
            raise PasswordRequired("the PDF is password-protected") from None
        raise UnsupportedType("the PDF could not be opened") from None
    try:
        if len(pdf) > max_pages:
            raise TooLarge(f"PDF exceeds {max_pages} pages")
        pages = []
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                image = page.render(scale=dpi / 72).to_pil().convert("RGB")
                words = _text_layer_words(page, index, image.width, image.height)
            finally:
                page.close()
            pages.append(Page(index, image, image.width, image.height, words))
        return pages
    finally:
        pdf.close()


def _is_password_error(e: Exception) -> bool:
    code = getattr(e, "err_code", None)
    if code is not None:
        return code == raw.FPDF_ERR_PASSWORD
    return "password" in str(e).lower()


def _text_layer_words(page, index: int, width: int, height: int) -> list[WordBox] | None:
    """The page's words with boxes when its text layer is genuine (visible text objects and no
    full-page image), else None."""
    if not _has_genuine_text(page):
        return None
    textpage = page.get_textpage()
    try:
        words = _words_from_chars(page, textpage, index, width, height)
    finally:
        textpage.close()
    return words or None


def _has_genuine_text(page) -> bool:
    """Visible text exists and no image covers FULL_PAGE_COVER of the page."""
    page_w, page_h = page.get_size()
    area = page_w * page_h
    visible_text = False
    for obj in page.get_objects():
        if obj.type == raw.FPDF_PAGEOBJ_TEXT:
            if raw.FPDFTextObj_GetTextRenderMode(obj) not in INVISIBLE_RENDER_MODES:
                visible_text = True
        elif obj.type == raw.FPDF_PAGEOBJ_IMAGE and area:
            left, bottom, right, top = obj.get_bounds()
            if (right - left) * (top - bottom) >= FULL_PAGE_COVER * area:
                return False
    return visible_text


def _words_from_chars(page, textpage, index: int, width: int, height: int) -> list[WordBox]:
    """Runs of non-space characters, each with the union of its character boxes, mapped to
    the rendered page's orientation."""
    words: list[WordBox] = []
    text = ""
    box: list[float] | None = None
    dev_w, dev_h = width * BOX_SCALE, height * BOX_SCALE
    dx, dy = ctypes.c_int(), ctypes.c_int()

    def to_device(x: float, y: float) -> tuple[int, int]:
        raw.FPDF_PageToDevice(page, 0, 0, dev_w, dev_h, 0, x, y, dx, dy)
        return dx.value, dy.value

    def flush() -> None:
        nonlocal text, box
        if text and box is not None:
            (ax, ay), (bx, by) = to_device(box[0], box[1]), to_device(box[2], box[3])
            x0, x1 = sorted((ax, bx))
            y0, y1 = sorted((ay, by))
            words.append(
                WordBox(
                    text,
                    index,
                    frac(x0, dev_w),
                    frac(y0, dev_h),
                    frac(x1, dev_w),
                    frac(y1, dev_h),
                )
            )
        text, box = "", None

    for i in range(textpage.count_chars()):
        ch = chr(raw.FPDFText_GetUnicode(textpage, i))
        if ch.isspace() or ch == "￾":
            flush()
            continue
        left, bottom, right, top = textpage.get_charbox(i)
        if right - left <= 0 and top - bottom <= 0:
            continue  # a control character without a glyph
        text += ch
        if box is None:
            box = [left, bottom, right, top]
        else:
            box = [min(box[0], left), min(box[1], bottom), max(box[2], right), max(box[3], top)]
    flush()
    return detach_colons(words)


# images -------------------------------------------------------------------------------------


def _image_pages(data: bytes, max_pages: int) -> list[Page]:
    try:
        img = Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        raise UnsupportedType("the image could not be decoded") from None
    pages = []
    with img:
        for index, frame in enumerate(ImageSequence.Iterator(img)):
            if index >= max_pages:
                raise TooLarge(f"image exceeds {max_pages} pages")
            page_image = ImageOps.exif_transpose(frame.copy()).convert("RGB")
            pages.append(Page(index, page_image, page_image.width, page_image.height, None))
    return pages
