"""Rulebook administration.

python -m ergplan.rulebook.cli sync-jurisdictions
python -m ergplan.rulebook.cli sync-golden
python -m ergplan.rulebook.cli restore            # load every committed approved rulebook
python -m ergplan.rulebook.cli export             # write approved versions to packages/rulebooks/states
python -m ergplan.rulebook.cli list
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from ..db.base import session_scope
from ..db.models import RulebookVersion
from . import golden, service, yaml_io


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ergplan.rulebook.cli")
    ap.add_argument("command", choices=["sync-jurisdictions", "sync-golden", "restore", "export", "list"])
    ap.add_argument("--actor", default="rulebook-cli")
    a = ap.parse_args(argv)
    if a.command == "sync-jurisdictions":
        with session_scope(actor=a.actor) as s:
            print("jurisdictions:", service.sync_jurisdictions(s))
    elif a.command == "sync-golden":
        with session_scope(actor=a.actor) as s:
            print("golden tests:", golden.sync_tests(s))
    elif a.command == "restore":
        with session_scope(actor=a.actor) as s:
            service.sync_jurisdictions(s)
            golden.sync_tests(s)
        for p in sorted(yaml_io.states_dir().rglob("*.yaml")):
            d = yaml_io.load(p)
            with session_scope(actor=d.get("approved_by") or a.actor, role="analyst") as s:
                exists = s.scalar(
                    select(RulebookVersion).where(
                        RulebookVersion.family == d["family"],
                        RulebookVersion.jurisdiction_id == d["jurisdiction"],
                        RulebookVersion.status == "approved",
                        RulebookVersion.title == d.get("title"),
                    )
                )
                if exists:
                    print("present", p.name)
                    continue
                v = yaml_io.restore(s, p)
                print("restored", p.name, "→", v.status)
    elif a.command == "export":
        with session_scope() as s:
            for p in yaml_io.export_approved(s):
                print(p)
    elif a.command == "list":
        with session_scope() as s:
            for v in s.scalars(
                select(RulebookVersion).order_by(RulebookVersion.jurisdiction_id, RulebookVersion.family)
            ):
                head = f"{v.jurisdiction_id:8} {v.family:18} v{v.version:<3} {v.status:10}"
                print(f"{head} golden={v.golden_status} {v.title or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
