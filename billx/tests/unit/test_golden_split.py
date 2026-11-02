"""The tuning / held-out split (section 12.1) and the model-SDK import boundary (rule 9)."""

import ast
import hashlib
import shutil
from pathlib import Path

from billx.core.settings import config_dir
from billx.platform.studio.golden import recorded_split, split_for

SHAS = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(200)]
ROOT = Path(__file__).resolve().parents[2] / "billx"


def test_split_is_deterministic_and_uses_both_halves():
    first = [split_for(s, 7) for s in SHAS]
    assert first == [split_for(s, 7) for s in SHAS]
    assert set(first) == {"tuning", "held_out"}
    assert first != [split_for(s, 8) for s in SHAS]  # the seed matters


def test_every_bill_is_tuning_until_stage_11():
    assert {recorded_split(s) for s in SHAS} == {"tuning"}


def test_held_out_flag_switches_to_the_seeded_split(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    shutil.copytree(config_dir(), cfg)
    studio = cfg / "studio.yaml"
    studio.write_text(
        studio.read_text().replace("held_out_enabled: false", "held_out_enabled: true")
    )
    monkeypatch.setenv("BILLX_CONFIG_DIR", str(cfg))
    assert [recorded_split(s) for s in SHAS] == [split_for(s, 20261012) for s in SHAS]


def test_only_providers_import_a_model_sdk():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if (ROOT / "reader" / "providers") in path.parents:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n.split(".")[0] in ("openai", "anthropic") for n in names):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
