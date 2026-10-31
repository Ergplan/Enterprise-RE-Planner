"""Stage 1 end-to-end on real input: the UPERC NPCL FY 2026-27 order's HV-2 rate schedule (PDF page 387)
read by the OpenAI reader, grounded, proposed as a draft, checked by golden tests written from the page,
approved, and exported. Needs data/corpus (the PDF from the Mac mini) and OPENAI_API_KEY."""

from pathlib import Path

import pytest

from ergplan.core.settings import REPO_ROOT, get_settings
from ergplan.db.base import session_scope
from ergplan.documents import corpus
from ergplan.regreader import direct
from ergplan.rulebook import golden, service, yaml_io

ROOT = REPO_ROOT / "data" / "corpus" / "India_DISCOM_Tariff_Orders_Final_2026"
EXPECTED = {
    (None, 11): ("300.00", "7.10"),
    (11, 66): ("290.00", "6.80"),
    (66, 132): ("270.00", "6.40"),
    (132, None): ("270.00", "6.10"),
}

pytestmark = [
    pytest.mark.external,
    pytest.mark.skipif(not (ROOT / "09_Uttar_Pradesh").exists(), reason="corpus PDFs not present"),
    pytest.mark.skipif(not get_settings().openai_api_key, reason="no OPENAI_API_KEY"),
]


def test_npcl_hv2_read_ground_approve_export(tmp_path: Path) -> None:
    corpus.register_corpus(ROOT)
    with session_scope(actor="e2e") as s:
        service.sync_jurisdictions(s)
        golden.sync_tests(s)
    with session_scope() as s:
        from sqlalchemy import select

        from ergplan.db.models import SourceDocument

        doc = s.scalar(select(SourceDocument).where(SourceDocument.file_sha256.like("ff36813e2671%")))
        assert doc is not None
        r = direct.read(
            s,
            document_id=doc.id,
            family="tariff_schedule",
            jurisdiction_id="npcl",
            pages=[387, 388],
            focus="Rate schedule HV-2, (A) Urban Schedule only, one row per supply-voltage band.",
        )
    assert len(r.accepted) == 4, [x.reasons for x in r.rejected]
    got = {
        (row["scope"]["voltage_kv"].get("min"), row["scope"]["voltage_kv"].get("max")): (
            row["body"]["demand_charge"]["value"],
            row["body"]["energy_charge"]["base"],
        )
        for row in r.accepted
    }
    assert got == EXPECTED
    assert all(row["source_ref"]["page"] == 387 for row in r.accepted)
    with session_scope(actor="e2e-analyst", role="analyst") as s:
        v = service.propose(
            s,
            family="tariff_schedule",
            jurisdiction_id="npcl",
            rows=r.accepted,
            actor="e2e-analyst",
            effective_from=doc.order_date,
            title="e2e",
        )
        service.approve(s, v.id, actor="e2e-analyst", role="analyst")
    with session_scope() as s:
        files = yaml_io.export_approved(s, root=tmp_path)
    assert any(f.name == "npcl-v1.yaml" for f in files)
