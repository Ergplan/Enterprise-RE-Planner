"""Engine import boundaries (section 10.4): reader, auditor and intelligence import core only."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "billx"
FORBIDDEN = {
    "reader": {"billx.auditor", "billx.intelligence", "billx.platform"},
    "auditor": {"billx.reader", "billx.intelligence", "billx.platform"},
    "intelligence": {"billx.reader", "billx.auditor", "billx.platform"},
    "core": {"billx.reader", "billx.auditor", "billx.intelligence", "billx.platform"},
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def violations(root: Path = ROOT) -> list[str]:
    out = []
    for engine, banned in FORBIDDEN.items():
        for path in (root / engine).rglob("*.py"):
            for name in _imports(path):
                if any(name == b or name.startswith(b + ".") for b in banned):
                    out.append(f"{path.relative_to(root.parent)} imports {name}")
    return out


def test_engines_import_core_only():
    assert violations() == []


def test_boundary_check_catches_a_violation(tmp_path):
    (tmp_path / "reader").mkdir()
    (tmp_path / "reader" / "x.py").write_text("from billx.auditor import formulas\n")
    for engine in ("auditor", "intelligence", "core"):
        (tmp_path / engine).mkdir()
    found = violations(tmp_path)
    assert len(found) == 1 and found[0].endswith("reader/x.py imports billx.auditor")
