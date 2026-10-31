"""The committed rulebooks (packages/rulebooks/states) restore into a clean database through the
golden gate and export back byte for byte: the watcher's 'regenerates without diff' check."""

from pathlib import Path

import pytest

from ergplan.db.base import session_scope
from ergplan.rulebook import golden, service, yaml_io


@pytest.mark.skipif(not any(yaml_io.states_dir().rglob("*.yaml")), reason="no committed rulebooks yet")
def test_committed_rulebooks_restore_and_export_identically(tmp_path: Path) -> None:
    with session_scope(actor="ci") as s:
        service.sync_jurisdictions(s)
        golden.sync_tests(s)
    files = sorted(yaml_io.states_dir().rglob("*.yaml"))
    for p in files:
        d = yaml_io.load(p)
        with session_scope(actor=d.get("approved_by") or "ci", role="analyst") as s:
            v = yaml_io.restore(s, p)
            assert v.status == "approved", p
    with session_scope() as s:
        written = yaml_io.export_approved(s, root=tmp_path)
    assert len(written) == len(files)
    for p in files:
        rel = p.relative_to(yaml_io.states_dir())
        assert (tmp_path / rel).read_text() == p.read_text(), rel
