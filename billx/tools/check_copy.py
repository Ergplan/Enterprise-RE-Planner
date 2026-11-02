"""CLAUDE.md and AGENTS.md must equal sections 1 to 5 of docs/build-prompt.md."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sections_1_to_5(prompt: str) -> str:
    lines = prompt.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith("## 1. Mission"))
    end = next(i for i, line in enumerate(lines) if line.startswith("## 6. The API"))
    return "".join(lines[start:end])


def problems(root: Path = ROOT) -> list[str]:
    expected = sections_1_to_5((root / "docs/build-prompt.md").read_text())
    return [
        f"{name} differs from sections 1-5 of docs/build-prompt.md"
        for name in ("CLAUDE.md", "AGENTS.md")
        if not (root / name).exists() or (root / name).read_text() != expected
    ]


def main() -> int:
    found = problems()
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
