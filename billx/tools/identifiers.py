"""Client-identifier search (rule 10, section 11 item 1).

Looks for consumer names, account numbers, GSTIN and PAN from the real bills in the
repository's tracked files, in a directory, or in an exported image filesystem (tar).
The identifiers come from the CLIENT_IDENTIFIERS environment variable (the CI secret,
one per line) and from ~/billx-data/client-identifiers.txt (one per line, # comments);
they are never stored in the repository. A hit is reported by path and identifier index
only, never by the identifier itself.

    python tools/identifiers.py                 # tracked files
    python tools/identifiers.py --path out/     # a directory
    python tools/identifiers.py --tar image.tar # an exported image
    python tools/identifiers.py --stdin         # a request body before it leaves (reviewer)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tarfile
from collections.abc import Iterable, Iterator
from pathlib import Path

DATA_DIR = Path(os.environ.get("BILLX_DATA_DIR", Path.home() / "billx-data"))
LOCAL_LIST = DATA_DIR / "client-identifiers.txt"
MAX_BYTES = 50 * 1024 * 1024
# The compact form (letters and digits only) is searched only for identifiers that hold
# a digit and are long enough not to match by accident across word boundaries.
COMPACT_MIN = 8


def load_identifiers() -> list[str]:
    raw = os.environ.get("CLIENT_IDENTIFIERS", "")
    lines = raw.replace(",", "\n").splitlines()
    if LOCAL_LIST.exists():
        lines += LOCAL_LIST.read_text().splitlines()
    out, seen = [], set()
    for line in lines:
        item = line.strip()
        if item and not item.startswith("#") and item.casefold() not in seen:
            seen.add(item.casefold())
            out.append(item)
    return out


def _spaced(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold())


def _compact(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.casefold())


class Matcher:
    def __init__(self, identifiers: list[str]):
        self.spaced = [_spaced(i) for i in identifiers]
        self.compact = [
            _compact(i) if re.search(r"\d", i) and len(_compact(i)) >= COMPACT_MIN else None
            for i in identifiers
        ]

    def hits(self, data: bytes) -> list[int]:
        text = data.decode("latin-1")
        spaced, compact = _spaced(text), None
        found = []
        for n, ident in enumerate(self.spaced):
            if ident in spaced:
                found.append(n)
                continue
            if self.compact[n]:
                compact = compact if compact is not None else _compact(text)
                if self.compact[n] in compact:
                    found.append(n)
        return found


def tracked_files(root: Path) -> Iterator[tuple[str, bytes]]:
    names = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    for name in filter(None, names):
        path = root / name.decode()
        if path.is_file() and path.stat().st_size <= MAX_BYTES:
            yield str(path.relative_to(root)), path.read_bytes()


def directory_files(root: Path) -> Iterator[tuple[str, bytes]]:
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.stat().st_size <= MAX_BYTES:
            yield str(path), path.read_bytes()


def tar_files(archive: Path) -> Iterator[tuple[str, bytes]]:
    with tarfile.open(archive) as tar:
        for member in tar:
            if member.isfile() and member.size <= MAX_BYTES:
                handle = tar.extractfile(member)
                if handle is not None:
                    yield member.name, handle.read()


def search(files: Iterable[tuple[str, bytes]], matcher: Matcher) -> list[tuple[str, int]]:
    return [(name, n) for name, data in files for n in matcher.hits(data)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--path", type=Path)
    source.add_argument("--tar", type=Path)
    source.add_argument("--stdin", action="store_true")
    parser.add_argument(
        "--require", action="store_true", help="fail when no identifiers are configured (CI)"
    )
    args = parser.parse_args(argv)

    identifiers = load_identifiers()
    if not identifiers:
        print("identifiers: none configured", file=sys.stderr)
        return 1 if args.require else 0
    matcher = Matcher(identifiers)
    if args.stdin:
        files: Iterable[tuple[str, bytes]] = [("<stdin>", sys.stdin.buffer.read())]
    elif args.tar:
        files = tar_files(args.tar)
    elif args.path:
        files = directory_files(args.path)
    else:
        files = tracked_files(Path(__file__).resolve().parents[1])
    found = search(files, matcher)
    for name, n in found:
        print(f"identifiers: HIT {name} (identifier #{n})")
    print(f"identifiers: {len(identifiers)} identifiers, {len(found)} hits", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
