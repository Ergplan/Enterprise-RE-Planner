"""The golden manifest: one append-only JSONL line per confirmed bill, under
<BILLX_DATA_DIR>/golden/manifest.jsonl, never in git. A correction appends a new entry; the
latest entry for a sha256 supersedes the earlier ones, which stay readable (rule 17).
"""

import hashlib
import json
from pathlib import Path

from billx.core.settings import data_dir, load_config

MANIFEST_VERSION = 1


def manifest_path() -> Path:
    return data_dir() / "golden" / "manifest.jsonl"


def split_for(sha256: str, seed: int) -> str:
    """The tuning / held-out half a bill belongs to, fixed by its sha256 and the seed."""
    digest = hashlib.sha256(f"{seed}:{sha256}".encode()).digest()
    return "held_out" if digest[0] % 2 else "tuning"


def recorded_split(sha256: str) -> str:
    """Every bill is `tuning` until Stage 11 sets split.held_out_enabled (section 12.1)."""
    cfg = load_config("studio.yaml")["split"]
    return split_for(sha256, int(cfg["seed"])) if cfg["held_out_enabled"] else "tuning"


def read_entries() -> list[dict]:
    path = manifest_path()
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def latest_by_sha() -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for entry in read_entries():
        latest[entry["sha256"]] = entry
    return latest


def append_entry(entry: dict) -> dict:
    """Append one entry; if the bill already has one, record which entry it supersedes."""
    previous = latest_by_sha().get(entry["sha256"])
    entry = {
        "manifest_version": MANIFEST_VERSION,
        **entry,
        "supersedes": previous["confirmed_at"] if previous else None,
    }
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    return entry
