"""Rulebooks as files. Approved versions are exported to
packages/rulebooks/states/<state>/<family>/<jurisdiction>-v<N>.yaml (deterministic text), and any
such file imports back as a draft, or is restored as approved through the same golden-test gate.
The committed files are how a fresh database (the Mac mini, the VM, CI) gets its rulebooks."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.settings import get_settings
from ..db.models import Jurisdiction, Rule, RulebookVersion
from . import service


class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_presenter)


def states_dir() -> Path:
    return get_settings().rulebooks_dir / "states"


def version_to_dict(session: Session, v: RulebookVersion) -> dict[str, Any]:
    rows = []
    for r in session.scalars(select(Rule).where(Rule.rulebook_version_id == v.id).order_by(Rule.position)):
        row: dict[str, Any] = {"label": r.label, "scope": r.scope, "body": r.body, "source_ref": r.source_ref}
        if r.field_refs:
            row["field_refs"] = r.field_refs
        rows.append({k: val for k, val in row.items() if val is not None})
    return {
        "family": v.family,
        "jurisdiction": v.jurisdiction_id,
        "version": v.version,
        "status": v.status,
        "title": v.title,
        "effective_from": v.effective_from.isoformat(),
        "effective_to": v.effective_to.isoformat() if v.effective_to else None,
        "origin": v.origin,
        "approved_by": v.approved_by,
        "rows": rows,
    }


def dump(d: dict[str, Any]) -> str:
    return yaml.dump(d, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=120)


def path_for(session: Session, v: RulebookVersion) -> Path:
    j = session.get(Jurisdiction, v.jurisdiction_id)
    state = (j.state_code if j and j.state_code else v.jurisdiction_id).lower()
    return states_dir() / state / v.family / f"{v.jurisdiction_id}-v{v.version}.yaml"


def export_approved(session: Session, root: Path | None = None) -> list[Path]:
    """Write every approved version to its file. Returns the paths written."""
    out = []
    for v in session.scalars(select(RulebookVersion).where(RulebookVersion.status == "approved")):
        p = path_for(session, v)
        if root is not None:
            p = root / p.relative_to(states_dir())
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(dump(version_to_dict(session, v)))
        out.append(p)
    return sorted(out)


def load(path: Path) -> dict[str, Any]:
    d = yaml.safe_load(path.read_text())
    if not isinstance(d, dict) or "family" not in d or "rows" not in d:
        raise ValueError(f"{path} is not a rulebook file")
    return d


def import_file(session: Session, path: Path, actor: str) -> RulebookVersion:
    """Import a rulebook file as a new draft."""
    d = load(path)
    return service.propose(
        session,
        family=d["family"],
        jurisdiction_id=d["jurisdiction"],
        rows=d["rows"],
        actor=actor,
        effective_from=date.fromisoformat(str(d["effective_from"])),
        effective_to=date.fromisoformat(str(d["effective_to"])) if d.get("effective_to") else None,
        title=d.get("title"),
        origin="yaml",
        notes=f"imported from {path.name}",
    )


def restore(session: Session, path: Path) -> RulebookVersion:
    """Import an approved file and approve it again through the golden gate, as its approver."""
    d = load(path)
    v = import_file(session, path, actor=d.get("approved_by") or "restore")
    if d.get("status") == "approved":
        service.approve(session, v.id, actor=d.get("approved_by") or "restore", role="analyst")
    return v
