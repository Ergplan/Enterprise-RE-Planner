"""The identifier search and the CLAUDE.md/AGENTS.md copy check."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


identifiers = _load("identifiers")
check_copy = _load("check_copy")


def test_identifier_found_in_spaced_and_compact_forms():
    m = identifiers.Matcher(["Synthetic Test Industries", "ABCDE1234F", "9004-2606-0417"])
    assert m.hits(b"bill for SYNTHETIC   test industries") == [0]
    assert m.hits(b"PAN: abcde 1234 f") == [1]
    assert m.hits(b"KNO 900426060417") == [2]
    assert m.hits(b"nothing to see") == []


def test_short_identifier_has_no_compact_form():
    m = identifiers.Matcher(["12-34"])
    assert m.hits(b"1234") == []


def test_report_names_the_identifier_index_never_the_identifier(tmp_path, capsys, monkeypatch):
    (tmp_path / "a.txt").write_text("account 99887766554")
    monkeypatch.setenv("CLIENT_IDENTIFIERS", "99887766554")
    monkeypatch.setattr(identifiers, "LOCAL_LIST", tmp_path / "missing.txt")
    assert identifiers.main(["--path", str(tmp_path)]) == 1
    out = capsys.readouterr()
    assert "identifier #0" in out.out
    assert "99887766554" not in out.out + out.err


def test_require_fails_without_identifiers(monkeypatch, tmp_path):
    monkeypatch.delenv("CLIENT_IDENTIFIERS", raising=False)
    monkeypatch.setattr(identifiers, "LOCAL_LIST", tmp_path / "missing.txt")
    assert identifiers.main(["--require", "--path", str(tmp_path)]) == 1
    assert identifiers.main(["--path", str(tmp_path)]) == 0


def test_agents_copy_matches_build_prompt():
    assert check_copy.problems() == []


def test_agents_copy_detects_drift(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/build-prompt.md").write_text("# t\n## 1. Mission\nx\n## 6. The API\ny\n")
    (tmp_path / "CLAUDE.md").write_text("## 1. Mission\nx\n")
    (tmp_path / "AGENTS.md").write_text("## 1. Mission\nchanged\n")
    assert check_copy.problems(tmp_path) == [
        "AGENTS.md differs from sections 1-5 of docs/build-prompt.md"
    ]


def test_ping_without_a_key_fails_without_a_network_call(monkeypatch, capsys):
    from billx.reader.providers import ping

    monkeypatch.setattr(ping, "load_env", lambda: None)
    for name in ("BILLX_OPENAI_API_KEY", "OPENAI_BUILD_REVIEW_KEY", "BILLX_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert ping.main(["openai:some-model"]) == 1
    assert ping.main(["anthropic:some-model"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "fail openai:some-model: RuntimeError",
        "fail anthropic:some-model: RuntimeError",
    ]
