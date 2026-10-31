"""Rule 9 and invariant 4, enforced by reading the source: only providers/ imports a model SDK,
and the computing packages never import providers/."""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "ergplan"
SDKS = {"openai", "anthropic"}
PURE = ["engine", "settlement", "optimizer", "rulebook"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            out.add(("." * node.level) + mod)
    return out


def test_only_providers_import_model_sdks() -> None:
    offenders = []
    for f in PKG.rglob("*.py"):
        if "providers" in f.relative_to(PKG).parts:
            continue
        if any(i.split(".")[0] in SDKS for i in _imports(f)):
            offenders.append(str(f.relative_to(PKG)))
    assert offenders == []


def test_pure_packages_never_import_providers() -> None:
    offenders = []
    for pkg in PURE:
        for f in (PKG / pkg).rglob("*.py"):
            if any("providers" in i for i in _imports(f)):
                offenders.append(str(f.relative_to(PKG)))
    assert offenders == []
