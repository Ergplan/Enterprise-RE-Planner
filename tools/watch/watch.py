#!/usr/bin/env python3
"""The watcher (master prompt 5.2). Re-runs every check when a source file changes and writes
tools/watch/status.json ({"green", "checks", "at"}) and tools/watch/watch.log. The agent reads
status.json before every commit; a red check blocks the commit.

  python3 tools/watch/watch.py          # watch (poll every 2 s)
  python3 tools/watch/watch.py --once   # run once, exit 1 if red (CI, pre-commit)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"
VENV = API / ".venv" / "bin"
PY = str(VENV / "python") if (VENV / "python").exists() else sys.executable
TOOL = lambda name: str(VENV / name) if (VENV / name).exists() else name  # noqa: E731
STATUS = ROOT / "tools" / "watch" / "status.json"
LOG = ROOT / "tools" / "watch" / "watch.log"
WATCHED = [API / "ergplan", API / "tests", API / "alembic", WEB / "app", WEB / "components", WEB / "lib",
           WEB / "tests", ROOT / "packages", ROOT / "docs" / "MASTER-PROMPT.md"]
SUFFIXES = {".py", ".ts", ".tsx", ".css", ".json", ".yaml", ".yml", ".md"}

CHECKS: list[tuple[str, list[str], Path]] = [
    ("ruff", [TOOL("ruff"), "check", "ergplan", "tests", "alembic"], API),
    ("ruff-format", [TOOL("ruff"), "format", "--check", "ergplan", "tests", "alembic"], API),
    ("mypy", [TOOL("mypy"), "ergplan"], API),
    ("pytest", [TOOL("pytest"), "-q", "-x"], API),
    ("alembic-drift", [TOOL("alembic"), "check"], API),
    ("web-typecheck", ["pnpm", "-s", "typecheck"], WEB),
    ("web-test", ["pnpm", "-s", "test"], WEB),
    ("rulebooks", [PY, "tools/dev/validate-rulebooks.py"], ROOT),
    ("field-trace", [PY, "tools/dev/field-trace.py", "--check"], ROOT),
    ("claude-md", ["bash", "-c", "cp CLAUDE.md /tmp/.cm && tools/dev/sync-claude-md.sh >/dev/null && diff -q /tmp/.cm CLAUDE.md"], ROOT),
]


def snapshot() -> float:
    latest = 0.0
    for base in WATCHED:
        paths = [base] if base.is_file() else base.rglob("*")
        for p in paths:
            if p.suffix in SUFFIXES and "node_modules" not in p.parts and ".next" not in p.parts:
                try:
                    latest = max(latest, p.stat().st_mtime)
                except OSError:
                    pass
    return latest


def run_all() -> bool:
    results = {}
    with LOG.open("a") as log:
        log.write(f"\n=== {datetime.now(UTC).isoformat()} ===\n")
        for name, cmd, cwd in CHECKS:
            t0 = time.time()
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env={**os.environ, "CI": "1"})
            ok = p.returncode == 0
            tail = (p.stdout + p.stderr).strip().splitlines()[-12:]
            results[name] = {"ok": ok, "seconds": round(time.time() - t0, 1), "tail": tail if not ok else tail[-1:]}
            log.write(f"[{'ok' if ok else 'FAIL'}] {name} ({results[name]['seconds']}s)\n")
            if not ok:
                log.write("\n".join(tail) + "\n")
    green = all(r["ok"] for r in results.values())
    STATUS.write_text(json.dumps({"green": green, "checks": results, "at": datetime.now(UTC).isoformat()}, indent=2))
    print(("GREEN" if green else "RED") + " · " + ", ".join(f"{k}{'' if v['ok'] else ' ✗'}" for k, v in results.items()))
    return green


def main() -> int:
    if "--once" in sys.argv:
        return 0 if run_all() else 1
    last = -1.0
    while True:
        now = snapshot()
        if now != last:
            last = now
            run_all()
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
