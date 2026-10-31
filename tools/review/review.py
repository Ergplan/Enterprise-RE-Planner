#!/usr/bin/env python3
"""Independent stage review (operating rule 16). A model from a different family than the builder
(OpenAI, REVIEWER_MODEL), in a fresh context, receives only: the stage diff, CLAUDE.md and the
stage prompt. It answers the fixed checklist and nothing else, as JSON. Writes
docs/stage-reports/stage-N-review.md and exits 1 when any finding is a code defect.

  tools/review/run.sh N
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDE = [":(exclude)apps/web/public/vendor", ":(exclude)apps/web/pnpm-lock.yaml", ":(exclude)packages/rulebooks/corpus",
           ":(exclude)apps/api/uv.lock", ":(exclude)docs/stage-reports", ":(exclude)packages/rulebooks/states",
           ":(exclude)*.pdf", ":(exclude)apps/api/tests/fixtures/billx/*.json"]
MAX_DIFF = 520_000  # about 130k tokens; code and tests are sent first so truncation drops data files, not code
CODE_FIRST = ["apps/api/ergplan", "apps/api/tests", "apps/api/alembic", "apps/web", "tools", "docker", "packages", "docs", "."]

CHECKLIST = """Answer this fixed checklist about the diff, citing file and line for every finding. Nothing else.
(a) Every invariant in CLAUDE.md section 3 upheld by the code in this diff, or the violation.
(b) Every API endpoint added in this diff has a test.
(c) Every write to the tables rules, rulebook_versions, runs is audited (if this stage touches them).
(d) Generated documents (docs/field-trace.md, CLAUDE.md, packages/rulebooks/states/) regenerate without diff, as far as the diff shows.
(e) Any claim in the draft stage report (if included in the diff) that the code does not support.
Also flag: floats used for money or energy; model SDK imports outside ergplan/providers; secrets in code.

Return JSON: {"summary": str, "findings": [{"check": "a|b|c|d|e|other", "kind": "code_defect|by_design|unprovable_from_diff|pending_decision",
"severity": "high|medium|low", "file": str, "line": int|null, "finding": str, "suggested_fix": str}]}.
Use kind=code_defect only for something the code in this diff gets wrong that a code change can fix."""


def sh(*args: str) -> str:
    out = subprocess.run(args, cwd=ROOT, capture_output=True, check=True).stdout
    return out.decode("utf-8", errors="replace")


def stage_prompt(n: int) -> str:
    src = (ROOT / "docs" / "MASTER-PROMPT.md").read_text()
    m = re.search(rf"### Stage {n} —.*?(?=\n### Stage {n + 1} —|\n---\n\n## 8\.)", src, re.S)
    return m.group(0) if m else f"(stage {n} prompt not found)"


def env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    n = int(sys.argv[1])
    base = sys.argv[2] if len(sys.argv) > 2 else f"stage-{n}-start"
    parts, seen = [], set()
    for path in CODE_FIRST:
        d = sh("git", "diff", base, "--", path, *EXCLUDE, *[f":(exclude){x}" for x in seen if x != "."])
        parts.append(d)
        seen.add(path)
    diff = "".join(parts)
    untracked = sh("git", "ls-files", "--others", "--exclude-standard")
    truncated = len(diff) > MAX_DIFF
    diff = diff[:MAX_DIFF]
    claude_md = (ROOT / "CLAUDE.md").read_text()
    user = (f"# CLAUDE.md\n{claude_md}\n\n# Stage prompt\n{stage_prompt(n)}\n\n# Untracked files (not in the diff)\n{untracked}\n\n"
            f"# Stage diff ({base}..working tree){' — TRUNCATED' if truncated else ''}\n{diff}\n\n# Checklist\n{CHECKLIST}")
    from openai import OpenAI  # the reviewer is a tool, not app code: rule 9 governs apps/api/ergplan only

    client = OpenAI(api_key=env("OPENAI_API_KEY"))
    model = env("REVIEWER_MODEL") or "gpt-5.1"
    r = client.chat.completions.create(
        model=model, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": "You are an independent senior reviewer of a staged software build. You have no other context."},
                  {"role": "user", "content": user}],
    )
    data = json.loads(r.choices[0].message.content or "{}")
    findings = data.get("findings", [])
    defects = [f for f in findings if f.get("kind") == "code_defect"]
    lines = [f"# Stage {n} independent review", "", f"Reviewer: {model} (OpenAI), fresh context. Diff {base}..working tree"
             + (" (truncated)" if truncated else "") + f". Tokens in/out: {r.usage.prompt_tokens}/{r.usage.completion_tokens}.", "",
             data.get("summary", ""), "", "| Check | Kind | Severity | Where | Finding | Suggested fix |", "| --- | --- | --- | --- | --- | --- |"]
    for f in findings:
        where = f"{f.get('file', '')}:{f.get('line') or ''}"
        lines.append(f"| {f.get('check')} | {f.get('kind')} | {f.get('severity')} | {where} | {f.get('finding', '').replace('|', '/')} | {f.get('suggested_fix', '').replace('|', '/')} |")
    out = ROOT / "docs" / "stage-reports" / f"stage-{n}-review.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"review: {len(findings)} findings, {len(defects)} code defects → {out.relative_to(ROOT)}")
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
