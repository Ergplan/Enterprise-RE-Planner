"""packages/rulebooks/jurisdictions.yaml names each regulator, state, group and DISCOM once, and every
parent exists (the sync is an upsert by id, so a duplicate would silently overwrite the first)."""

from __future__ import annotations

from collections import Counter

import yaml

from ergplan.core.settings import get_settings


def test_every_id_appears_once_and_parents_exist() -> None:
    data = yaml.safe_load((get_settings().rulebooks_dir / "jurisdictions.yaml").read_text())
    ids = [r["id"] for kind in ("regulators", "states", "groups", "discoms") for r in data[kind]]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    assert not dupes, dupes
    known = set(ids)
    for r in data["discoms"] + data["groups"]:
        assert r["state"] in known, r
        assert r.get("parent") is None or r["parent"] in known, r
