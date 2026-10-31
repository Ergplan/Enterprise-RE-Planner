"""Plain views of rule rows handed to engines and the UI (no ORM objects leave the rulebook)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..core.sourced import SourceRef


@dataclass(frozen=True)
class RuleView:
    id: str
    family: str
    version_id: str
    jurisdiction_id: str
    scope: dict[str, Any]
    body: dict[str, Any]
    source_ref: dict[str, Any]
    field_refs: dict[str, Any] = field(default_factory=dict)
    label: str | None = None
    position: int = 0
    effective_from: date | None = None
    effective_to: date | None = None

    def ref(self, pointer: str | None = None) -> SourceRef:
        """The citation for a body field (JSON pointer like /energy_charge/base), else the row's."""
        raw = (self.field_refs or {}).get(pointer or "") or self.source_ref
        return SourceRef(**{**raw, "rule_id": self.id})

    def get(self, pointer: str) -> Any:
        """Read a JSON pointer from the row ('/body/energy_charge/base' or '/energy_charge/base')."""
        node: Any = {"body": self.body, "scope": self.scope}
        parts = [p for p in pointer.split("/") if p]
        if parts and parts[0] not in ("body", "scope"):
            parts = ["body", *parts]
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            elif isinstance(node, list) and p.isdigit() and int(p) < len(node):
                node = node[int(p)]
            else:
                return None
        return node
