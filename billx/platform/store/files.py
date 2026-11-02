"""The file store (build prompt Stage 2.2): a folder per job under `<root>/jobs/<job_id>/`,
holding the uploaded file as `input<suffix>`, the rendered result as `result.json` and
any corrections as `feedback.jsonl`.

Nothing outside `<root>/jobs/` is ever read, written or deleted. A job_id is accepted only
when it is made of `[0-9a-f-]` (the store's UUIDs), and every folder path is resolved and
checked to lie under `<root>/jobs/` before use, so a crafted id cannot reach another path.
Deleting a job removes its whole folder at once (contract 1.0 section 4.4).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from billx.platform.store._json import dumps_exact

_JOB_ID = re.compile(r"[0-9a-f-]{1,64}")
_SUFFIX = re.compile(r"(\.[0-9a-z]{1,8})?")

RESULT_NAME = "result.json"
FEEDBACK_NAME = "feedback.jsonl"
INPUT_STEM = "input"


class BadJobId(ValueError):
    """A job_id that is not one of the store's own ids; the folder is never touched."""


class FileStore:
    """Job folders under `<root>/jobs/`."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._jobs_dir_resolved = self.jobs_dir.resolve()

    def folder(self, job_id: str) -> Path:
        """`<root>/jobs/<job_id>`; raises `BadJobId` for anything but `[0-9a-f-]{1,64}` or a
        path that would resolve outside the jobs folder."""
        if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
            raise BadJobId("job_id is not a store id")
        folder = self.jobs_dir / job_id
        resolved = folder.resolve()
        if resolved.parent != self._jobs_dir_resolved:
            raise BadJobId("job_id resolves outside the jobs folder")
        return folder

    def put(self, job_id: str, data: bytes, suffix: str) -> Path:
        """Write the uploaded bytes as `input<suffix>` and return the path. `suffix` is an
        extension such as `.pdf` (or empty); anything else is refused."""
        if not isinstance(suffix, str) or not _SUFFIX.fullmatch(suffix):
            raise ValueError("suffix must be an extension like .pdf")
        folder = self.folder(job_id)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{INPUT_STEM}{suffix}"
        _write_atomic(target, data)
        return target

    def input_path(self, job_id: str) -> Path:
        """The stored upload (`input<suffix>`, whatever `put` was given as suffix); raises
        `FileNotFoundError` when the job has none."""
        folder = self.folder(job_id)
        if folder.is_dir():
            for entry in sorted(folder.iterdir()):
                if entry.is_file() and entry.name.split(".", 1)[0] == INPUT_STEM:
                    return entry
        raise FileNotFoundError(f"job {job_id} has no input file")

    def result_path(self, job_id: str) -> Path:
        """Where the job's result JSON lives (whether or not it has been written)."""
        return self.folder(job_id) / RESULT_NAME

    def write_result(self, job_id: str, text: str) -> Path:
        """Write the rendered result (already JSON text) and return its path."""
        path = self.result_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, text.encode("utf-8"))
        return path

    def read_result(self, job_id: str) -> str | None:
        """The result text, or None when none has been written."""
        path = self.result_path(job_id)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def append_feedback(self, job_id: str, record: dict) -> None:
        """Append one JSON line to the job's `feedback.jsonl` (contract 1.0 section 4.5);
        it goes with the folder, so a correction's values live no longer than the job."""
        if not isinstance(record, dict):
            raise TypeError("a feedback record is a dict")
        line = dumps_exact(record, "record")
        path = self.folder(job_id) / FEEDBACK_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def delete(self, job_id: str) -> bool:
        """Remove the whole job folder at once; True when it existed."""
        folder = self.folder(job_id)
        if not folder.exists():
            return False
        shutil.rmtree(folder)
        return True

    def job_ids(self) -> list[str]:
        """The ids of every folder present (for the sweeper's orphan check)."""
        return sorted(p.name for p in self.jobs_dir.iterdir() if p.is_dir())

    def folder_mtime(self, job_id: str) -> int:
        """The folder's modification time as Unix seconds (an int)."""
        return int(self.folder(job_id).stat().st_mtime)


def _write_atomic(target: Path, data: bytes) -> None:
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


__all__ = ["FEEDBACK_NAME", "INPUT_STEM", "RESULT_NAME", "BadJobId", "FileStore"]
