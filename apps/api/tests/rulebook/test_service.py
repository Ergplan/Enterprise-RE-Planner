from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from ergplan.db.base import session_scope
from ergplan.db.models import AuditLog, RulebookVersion, RuleTest
from ergplan.rulebook import repository, sandbox, service
from tests.rulebook.helpers import EFFECTIVE, GOLDEN, ROWS

pytestmark = pytest.mark.usefixtures("jurisdictions")


def _add_golden(jid: str = "npcl", family: str = "tariff_schedule") -> None:
    with session_scope(actor="analyst@jw") as s:
        for t in GOLDEN:
            s.add(
                RuleTest(
                    jurisdiction_id=jid, family=family, name=t["name"], given=t["given"], expect=t["expect"]
                )
            )


def _propose(rows=ROWS) -> str:
    with session_scope(actor="analyst@jw") as s:
        v = service.propose(
            s,
            family="tariff_schedule",
            jurisdiction_id="npcl",
            rows=rows,
            actor="analyst@jw",
            effective_from=EFFECTIVE,
            title="NPCL FY 2026-27",
        )
        return v.id


def _approve(vid: str, role: str = "analyst") -> None:
    with session_scope(actor="analyst@jw", role=role) as s:
        service.approve(s, vid, actor="analyst@jw", role=role)


def test_write_without_actor_is_refused_by_the_database() -> None:
    with pytest.raises(DBAPIError, match=r"no ergplan\.actor"), session_scope() as s:
        service.propose(
            s,
            family="tariff_schedule",
            jurisdiction_id="npcl",
            rows=ROWS,
            actor="x",
            effective_from=EFFECTIVE,
        )


def test_invalid_rows_are_rejected_with_paths() -> None:
    bad = [{**ROWS[0], "body": {"category": "HV-2"}}]
    with pytest.raises(service.InvalidRows) as e, session_scope(actor="a") as s:
        service.propose(
            s, family="tariff_schedule", jurisdiction_id="npcl", rows=bad, actor="a", effective_from=EFFECTIVE
        )
    assert "billing_basis" in str(e.value)


def test_unknown_jurisdiction() -> None:
    with pytest.raises(service.UnknownJurisdiction), session_scope(actor="a") as s:
        service.propose(
            s,
            family="tariff_schedule",
            jurisdiction_id="nowhere",
            rows=ROWS,
            actor="a",
            effective_from=EFFECTIVE,
        )


def test_absurd_draft_is_invisible_to_engines() -> None:
    """Invariant 2: a draft with an absurd rate never reaches approved_rules."""
    _add_golden()
    vid = _propose()
    _approve(vid)
    absurd = [{**ROWS[0], "body": {**ROWS[0]["body"], "energy_charge": {"base": "999.99"}}}, ROWS[1]]
    _propose(absurd)
    with session_scope() as s:
        hits = repository.applicable(
            s, "tariff_schedule", "npcl", {"category": "HV-2", "voltage_kv": 11}, date(2026, 8, 1)
        )
        assert [h.body["energy_charge"]["base"] for h in hits] == ["8.32"]
        drafts = [
            r
            for v in s.scalars(select(RulebookVersion).where(RulebookVersion.status == "draft"))
            for r in sandbox.rules(s, v.id)
        ]
        assert any(r.body["energy_charge"]["base"] == "999.99" for r in drafts)


def test_approval_needs_analyst_role_in_service_and_database() -> None:
    _add_golden()
    vid = _propose()
    with pytest.raises(service.ApprovalRefused):
        _approve(vid, role="client")
    with session_scope(actor="intruder", role="client") as s:
        service.run_golden(s, vid)
    with pytest.raises(DBAPIError, match="role analyst"), session_scope(actor="intruder", role="client") as s:
        s.execute(text("update rulebook_versions set status='approved' where id=:i"), {"i": vid})


def test_approval_needs_green_golden_tests() -> None:
    vid = _propose()
    with pytest.raises(service.ApprovalRefused, match="0 of 0"):
        _approve(vid)
    _add_golden()
    wrong = _propose([ROWS[0]])  # no row for above 11 kV → the 33 kV test fails
    with pytest.raises(service.ApprovalRefused, match="2 of 3"):
        _approve(wrong)
    with (
        pytest.raises(DBAPIError, match="golden tests passed"),
        session_scope(actor="a", role="analyst") as s,
    ):
        s.execute(
            text("update rulebook_versions set status='approved', golden_status='green' where id=:i"),
            {"i": wrong},
        )


def test_approved_rows_are_frozen_and_a_new_approval_supersedes() -> None:
    _add_golden()
    v1 = _propose()
    _approve(v1)
    with pytest.raises(DBAPIError, match="cannot change"), session_scope(actor="a") as s:
        s.execute(text("update rules set label='x' where rulebook_version_id=:i"), {"i": v1})
    with session_scope(actor="analyst@jw") as s:
        v2 = service.duplicate(s, v1, actor="analyst@jw").id
    _approve(v2)
    with session_scope() as s:
        assert s.get(RulebookVersion, v1).status == "superseded"
        assert s.get(RulebookVersion, v2).status == "approved"
        assert len(repository.approved_rules(s, "tariff_schedule", ["npcl"], date(2026, 8, 1))) == 2


def test_every_write_is_audited_with_its_actor() -> None:
    _propose()
    with session_scope() as s:
        logs = list(s.scalars(select(AuditLog)))
        assert {log.table_name for log in logs} == {"rulebook_versions", "rules"}
        assert {log.actor for log in logs} == {"analyst@jw"}


def test_effective_dates_bound_what_engines_see() -> None:
    _add_golden()
    vid = _propose()
    _approve(vid)
    with session_scope() as s:
        assert repository.approved_rules(s, "tariff_schedule", ["npcl"], date(2026, 7, 1)) == []


def test_jurisdiction_chain() -> None:
    with session_scope() as s:
        assert service.jurisdiction_chain(s, "pvvnl") == ["pvvnl", "uppcl", "UP", "CERC"]
        assert service.jurisdiction_chain(s, "npcl") == ["npcl", "UP", "CERC"]


def test_view_itself_hides_rules_outside_their_dates() -> None:
    """A raw query of rules_approved (not through the repository) still respects the evaluation date."""
    _add_golden()
    vid = _propose()
    _approve(vid)
    with session_scope() as s:
        s.execute(text("select set_config('ergplan.on_date', '2026-07-01', true)"))
        assert s.execute(text("select count(*) from rules_approved")).scalar_one() == 0
        s.execute(text("select set_config('ergplan.on_date', '2026-08-01', true)"))
        assert s.execute(text("select count(*) from rules_approved")).scalar_one() == 2


def test_the_rules_cache_sees_an_approval_at_once() -> None:
    """Stage 8 caches approved rows per process; approving or superseding a version clears it."""
    _add_golden()
    with session_scope() as s:
        assert repository.approved_rules(s, "tariff_schedule", ["npcl"], date(2026, 8, 1)) == []
    vid = _propose()
    _approve(vid)
    with session_scope() as s:
        rows = repository.approved_rules(s, "tariff_schedule", ["npcl"], date(2026, 8, 1))
        assert [r.version_id for r in rows] and {r.version_id for r in rows} == {vid}
        again = repository.approved_rules(s, "tariff_schedule", ["npcl"], date(2026, 8, 1))
        assert [r.id for r in again] == [r.id for r in rows]
