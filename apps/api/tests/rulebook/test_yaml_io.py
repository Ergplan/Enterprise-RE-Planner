from pathlib import Path

import pytest

from ergplan.db.base import session_scope
from ergplan.db.models import RuleTest
from ergplan.rulebook import service, yaml_io
from tests.rulebook.helpers import EFFECTIVE, GOLDEN, ROWS

pytestmark = pytest.mark.usefixtures("jurisdictions")


def test_export_restore_round_trip_is_byte_identical(tmp_path: Path) -> None:
    with session_scope(actor="analyst@jw", role="analyst") as s:
        for t in GOLDEN:
            s.add(
                RuleTest(
                    jurisdiction_id="npcl",
                    family="tariff_schedule",
                    name=t["name"],
                    given=t["given"],
                    expect=t["expect"],
                )
            )
        s.flush()
        v = service.propose(
            s,
            family="tariff_schedule",
            jurisdiction_id="npcl",
            rows=ROWS,
            actor="analyst@jw",
            effective_from=EFFECTIVE,
            title="NPCL FY 2026-27",
        )
        service.approve(s, v.id, actor="analyst@jw", role="analyst")
    first = tmp_path / "a"
    with session_scope() as s:
        [p1] = yaml_io.export_approved(s, root=first)
    assert p1.relative_to(first).as_posix() == "up/tariff_schedule/npcl-v1.yaml"
    with session_scope(actor="analyst@jw", role="analyst") as s:
        v2 = yaml_io.restore(s, p1)
        assert v2.status == "approved" and v2.version == 2
        old = yaml_io.version_to_dict(s, v2)
    text1 = p1.read_text()
    old["version"], old["origin"] = 1, "regreader_direct" if "regreader" in text1 else old["origin"]
    d1 = yaml_io.load(p1)
    assert old["rows"] == d1["rows"]
    assert yaml_io.dump(d1) == text1
