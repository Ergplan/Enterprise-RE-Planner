"""A studio workspace: <BILLX_DATA_DIR>/workspaces/<name>/, holding the source folders the
person pointed it at, the bills found there (by sha256 and path; files are never copied),
rendered page images, cached pre-fills and the model usage log.
"""

import hashlib
import json
import logging
from pathlib import Path

import pypdfium2 as pdfium

from billx.core.settings import data_dir, load_config
from billx.reader.providers.base import Page

log = logging.getLogger(__name__)

_IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def resolve_workspace(arg: str | None) -> Path:
    """A bare name lives under <data>/workspaces/; a path is used as given."""
    if arg and (Path(arg).is_absolute() or "/" in arg or arg.startswith("~")):
        return Path(arg).expanduser()
    return data_dir() / "workspaces" / (arg or "default")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_input_kind(path: Path) -> str:
    """digital_pdf when a PDF has text on any page, scan otherwise; JPEG photo, PNG scan.
    Only a guess: the person corrects it in the studio."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            pdf = pdfium.PdfDocument(path)
        except pdfium.PdfiumError:
            return "scan"
        try:
            for page in pdf:
                if page.get_textpage().get_text_bounded().strip():
                    return "digital_pdf"
        finally:
            pdf.close()
        return "scan"
    return "photo" if suffix in (".jpg", ".jpeg") else "scan"


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.name = root.name
        root.mkdir(parents=True, exist_ok=True)
        self.state_path = root / "workspace.json"
        self.usage_log = root / "usage.jsonl"
        self.cfg = load_config("studio.yaml")

    def _state(self) -> dict:
        if self.state_path.is_file():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"sources": [], "bills": {}}

    def _save(self, state: dict) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.state_path)

    @property
    def sources(self) -> list[str]:
        return self._state()["sources"]

    @property
    def bills(self) -> dict[str, dict]:
        return self._state()["bills"]

    def add_source(self, folder: Path) -> int:
        """Scan a folder (recursively) for bills; returns how many new bills were added."""
        folder = folder.expanduser().resolve()
        if not folder.is_dir():
            raise NotADirectoryError(str(folder))
        state = self._state()
        if str(folder) not in state["sources"]:
            state["sources"].append(str(folder))
        suffixes = set(self.cfg["bill_suffixes"])
        added = 0
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix.lower() not in suffixes:
                continue
            sha = sha256_of(path)
            if sha in state["bills"]:
                continue
            state["bills"][sha] = {
                "path": str(path),
                "name": path.name,
                "input_kind": guess_input_kind(path),
            }
            added += 1
        self._save(state)
        log.info("workspace=%s source added, %d new bills", self.name, added)
        return added

    def path_of(self, sha: str) -> Path:
        """The bill's file, checked against its sha256 so a changed file is never shown."""
        bill = self.bills.get(sha)
        if bill is None:
            raise KeyError(sha)
        path = Path(bill["path"])
        if not path.is_file() or sha256_of(path) != sha:
            raise FileNotFoundError(f"bill {sha[:12]} is missing or changed since it was added")
        return path

    def pages(self, sha: str) -> list[Page]:
        """The bill's page images: a JPEG or PNG as it is, a PDF rendered with pypdfium2
        (cached in the workspace)."""
        path = self.path_of(sha)
        suffix = path.suffix.lower()
        if suffix in _IMAGE_MIME:
            return [Page(_IMAGE_MIME[suffix], path.read_bytes())]
        cache = self.root / "pages" / sha
        if not cache.is_dir():
            tmp = cache.with_suffix(".tmp")
            tmp.mkdir(parents=True, exist_ok=True)
            pdf = pdfium.PdfDocument(path)
            try:
                for i, page in enumerate(pdf):
                    image = page.render(scale=self.cfg["render_scale"]).to_pil()
                    image.save(tmp / f"{i:03d}.png")
            finally:
                pdf.close()
            tmp.replace(cache)
        return [Page("image/png", p.read_bytes()) for p in sorted(cache.glob("*.png"))]

    def _prefill_path(self, sha: str, bill_kind: str) -> Path:
        return self.root / "prefill" / f"{sha}.{bill_kind}.json"

    def cached_prefill(self, sha: str, bill_kind: str) -> dict | None:
        path = self._prefill_path(sha, bill_kind)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def save_prefill(self, sha: str, bill_kind: str, prefill: dict) -> None:
        path = self._prefill_path(sha, bill_kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prefill, sort_keys=True, ensure_ascii=False), encoding="utf-8")
