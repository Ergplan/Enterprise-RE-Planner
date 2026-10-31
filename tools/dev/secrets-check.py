#!/usr/bin/env python3
"""Fail when a file git tracks (or is about to track) looks like it holds a secret: API keys, private
keys, tokens, or a filled-in .env. Rule 11: secrets by environment variable only. Run by the watcher
and CI; prints the file and line (never the value)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    "OpenAI key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    "Anthropic key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "Slack token": re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{20,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}
ASSIGN = re.compile(r"^(OPENAI_API_KEY|BILLX_TOKEN|ERGPLAN_SECRET|ERGPLAN_SMTP_URL|TARIFF_ODER_TOKEN|BILLX_OPENAI_API_KEY)=(.+)$")
ALLOWED_VALUES = {"", "change-me-long-random", "dev-billx-token", "stub"}
SKIP_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".zip"}


def tracked() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    return [ROOT / p for p in out if p]


def main() -> int:
    bad = []
    for p in tracked():
        if p.suffix.lower() in SKIP_SUFFIXES or not p.is_file():
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        rel = p.relative_to(ROOT)
        if rel.name == ".env":
            bad.append(f"{rel}: a .env file must not be committed")
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS.items():
                if rx.search(line) and "secrets-check: allow" not in line:
                    bad.append(f"{rel}:{n}: looks like an {name}")
            m = ASSIGN.match(line.strip())
            if m and m.group(2).strip().strip('"') not in ALLOWED_VALUES and rel.name.startswith(".env"):
                bad.append(f"{rel}:{n}: {m.group(1)} has a value")
    for b in bad:
        print("secrets:", b)
    print("secrets: OK" if not bad else f"secrets: FAIL ({len(bad)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
