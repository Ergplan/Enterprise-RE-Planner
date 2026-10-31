#!/usr/bin/env python3
"""Run the Stage 1 reading plan (packages/rulebooks/seed/stage1-jobs.yaml) through the direct reader
and write one draft version per job. Prints accepted and rejected rows. Never approves."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import select  # noqa: E402

from ergplan.db.base import session_scope  # noqa: E402
from ergplan.db.models import SourceDocument  # noqa: E402
from ergplan.regreader import direct  # noqa: E402
from ergplan.rulebook import service  # noqa: E402

ACTOR = "build-agent@ergplan"


def main() -> int:
    plan = yaml.safe_load((ROOT / "packages/rulebooks/seed/stage1-jobs.yaml").read_text())
    only = sys.argv[1:]
    with session_scope(actor=ACTOR) as s:
        service.sync_jurisdictions(s)
    for job in plan["jobs"]:
        tag = f"{job['jurisdiction']}/{job['family']}"
        if only and tag not in only:
            continue
        with session_scope() as s:
            doc = s.scalar(select(SourceDocument).where(SourceDocument.file_sha256.like(job["document"] + "%")))
            if doc is None:
                print(f"!! {tag}: document {job['document']} not registered")
                continue
            r = direct.read(s, document_id=doc.id, family=job["family"], jurisdiction_id=job["jurisdiction"],
                            pages=job["pages"], focus=job["focus"],
                            pages_per_call=job.get("pages_per_call", direct.PAGES_PER_CALL))
            eff, title = doc.effective_from or doc.order_date, f"{doc.title} · pages {job['pages'][0]}–{job['pages'][-1]}"
        print(f"== {tag}: {len(r.accepted)} accepted, {len(r.rejected)} rejected ({r.tokens_in}/{r.tokens_out} tokens)")
        for row in r.accepted:
            print("   +", row.get("label"), json.dumps(row["scope"]), json.dumps(row["body"])[:220], "p", row["source_ref"]["page"])
        for x in r.rejected:
            print("   -", x.row.get("label"), x.reasons)
        if r.not_found or r.notes:
            print("   not_found:", r.not_found, "notes:", r.notes)
        if r.accepted:
            with session_scope(actor=ACTOR) as s:
                v = service.propose(s, family=job["family"], jurisdiction_id=job["jurisdiction"], rows=r.accepted,
                                    actor=ACTOR, effective_from=eff, title=title, origin="regreader_direct",
                                    notes=f"focus: {job['focus']}")
                print("   draft", v.id, "v", v.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
