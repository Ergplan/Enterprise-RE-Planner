"""The watcher: runs the build's checks and writes .status/checks.json.

    python tools/watch/watch.py --once   # one pass, exit 1 if any check fails
    python tools/watch/watch.py          # re-run whenever a tracked file changes

Checks: ruff, pytest (all cores, half when the studio is in use), the CLAUDE.md and
AGENTS.md copy check, the client-identifier search, and the engine import-boundary test.
Only check names, results, timings and the tail of failing output are written; the
identifier search never prints an identifier.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / ".status" / "checks.json"
PY = sys.executable
STUDIO_PORT = int(os.environ.get("BILLX_STUDIO_PORT", "8750"))


def _studio_in_use() -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", STUDIO_PORT)) == 0


def checks() -> dict[str, list[str]]:
    workers = str(max(1, (os.cpu_count() or 2) // 2)) if _studio_in_use() else "auto"
    return {
        "ruff": [PY, "-m", "ruff", "check", "."],
        "ruff_format": [PY, "-m", "ruff", "format", "--check", "."],
        "pytest": [PY, "-m", "pytest", "-q", "-n", workers, "tests/unit"],
        "agents_copy": [PY, "tools/check_copy.py"],
        "identifiers": [PY, "tools/identifiers.py"],
        "import_boundary": [PY, "-m", "pytest", "-q", "tests/unit/test_import_boundary.py"],
    }


def run_once() -> dict:
    results = {}
    for name, cmd in checks().items():
        started = time.monotonic()
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        results[name] = {
            "ok": proc.returncode == 0,
            "seconds": round(time.monotonic() - started, 1),
            "tail": "" if proc.returncode == 0 else (proc.stdout + proc.stderr)[-2000:],
        }
    status = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "ok": all(r["ok"] for r in results.values()),
        "checks": results,
    }
    STATUS.parent.mkdir(exist_ok=True)
    STATUS.write_text(json.dumps(status, indent=2) + "\n")
    return status


def _fingerprint() -> str:
    out = subprocess.run(
        ["git", "ls-files", "-m", "-o", "--exclude-standard", "-s", "--cached"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    mtimes = []
    for line in out.splitlines():
        path = ROOT / line.split("\t")[-1]
        if path.exists():
            mtimes.append(f"{path}:{path.stat().st_mtime_ns}")
    return "\n".join(sorted(mtimes))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    if args.once:
        status = run_once()
        print(" ".join(f"{k}={'ok' if v['ok'] else 'FAIL'}" for k, v in status["checks"].items()))
        return 0 if status["ok"] else 1
    last = None
    while True:
        current = _fingerprint()
        if current != last:
            last = current
            status = run_once()
            print(status["time"], "green" if status["ok"] else "RED", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
