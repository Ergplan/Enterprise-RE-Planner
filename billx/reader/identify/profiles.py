"""Utility profiles (build prompt section 7, Developer Guide section 7): YAML under `profiles/`,
one folder per discom with `discom.yaml` and `versions/<effective-from>.yaml`, plus
`_common.yaml` shared by every profile. Folders starting with `_` are skipped.

Every number in a profile is loaded as a `Decimal` (the YAML loader never builds a float),
so a tariff parameter reaches a rule exactly as written. `check_version` validates a version
file, including the `ast` allow-list over its rules' expressions, so a bad expression is
refused when the version is saved and not only when it is evaluated.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from billx.reader.validate.expr import (
    ALLOWED_HELPERS,
    ExpressionError,
    referenced_params,
    validate_expression,
)

_REPO_PROFILES = Path(__file__).resolve().parents[3] / "profiles"
_MONTH = re.compile(r"^\d{4}-\d{2}$")
STATUSES = ("draft", "final")
VERSION_KEYS = {
    "version",
    "effective_from",
    "status",
    "layout_ids",
    "layout_match",
    "prompt_hints",
    "printed_units",
    "params",
    "params_notes",
    "params_history",
    "tariff_order",
    "generic_tolerances",
    "labels",
    "label_map",
    "field_map",
    "rules",
    "template",
    "tod_complete",
    "bill_month_offset",
    "based_on",
    "review_notes",
    "finalized_by",
    "finalized_at",
    "notes",
}
RULE_KEYS = {
    "id",
    "description",
    "severity",
    "tolerance",
    "rel_tolerance",
    "actual",
    "expected",
    "detects",
}
DISCOM_KEYS = {"id", "name", "state", "bill_type", "match", "extends", "label_map", "notes"}
TEMPLATE_KEYS = {"required_fields", "line_items", "meters", "drift_threshold", "anchors"}


class ProfileError(ValueError):
    """A profile that cannot be loaded or a selection that cannot be made (ids only)."""


class _DecimalLoader(yaml.SafeLoader):
    """A YAML loader whose numbers are Decimal: `7.30` stays `Decimal("7.30")`, never a float."""


def _construct_decimal(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> Decimal:
    text = loader.construct_scalar(node).replace("_", "")
    try:
        return Decimal(text)
    except InvalidOperation as e:  # .inf, .nan and the like have no place in a profile
        raise ProfileError(f"not a decimal number at {node.start_mark}") from e


_DecimalLoader.add_constructor("tag:yaml.org,2002:float", _construct_decimal)
# ints stay ints for counts (drift_threshold, offsets); Decimal(int) is exact where needed.


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_DecimalLoader)  # noqa: S506 - SafeLoader subclass


def profiles_dir() -> Path:
    """`BILLX_PROFILES_DIR` ahead of the repository's `profiles/` (guide section 7)."""
    return Path(os.environ.get("BILLX_PROFILES_DIR", _REPO_PROFILES))


@lru_cache(maxsize=8)
def common(root: Path | None = None) -> dict:
    """`_common.yaml`: label synonyms, the element catalogue, the label map, the field map."""
    return load_yaml((root or profiles_dir()) / "_common.yaml") or {}


# the loaded profile ------------------------------------------------------------------------


@dataclass(frozen=True)
class Discom:
    id: str
    name: str
    state: str | None
    bill_type: str
    match: tuple[str, ...]
    extends: str | None
    label_map: tuple[dict, ...]
    path: Path


@dataclass(frozen=True)
class ProfileVersion:
    """One layout and tariff period of one discom, with its inheritance resolved."""

    discom: Discom
    version: str
    effective_from: str  # YYYY-MM
    status: str  # draft | final
    layout_ids: tuple[str, ...] = ()
    # a regex the bill's text must match for this version's rules, params and template to
    # apply (its arithmetic belongs to one layout); None: they apply to every bill
    layout_match: str | None = None
    params: dict[str, Decimal] = field(default_factory=dict)
    params_notes: dict[str, dict] = field(default_factory=dict)
    params_history: tuple[dict, ...] = ()
    tariff_order: dict | None = None
    generic_tolerances: dict[str, Decimal] = field(default_factory=dict)
    labels: dict[str, tuple[str, ...]] = field(default_factory=dict)
    label_map: tuple[dict, ...] = ()
    field_map: dict[str, str] = field(default_factory=dict)
    rules: tuple[dict, ...] = ()
    template: dict | None = None
    tod_complete: bool = False
    bill_month_offset: tuple[int, int] = (0, 1)
    prompt_hints: tuple[str, ...] = ()
    # fields this layout prints in another unit than the field list's: each entry
    # {paths, unit, when}; on a bill whose text matches `when` the value keeps the figure as
    # printed and carries `unit` (the team's decision: never converted)
    printed_units: tuple[dict, ...] = ()
    out_of_range: bool = False
    inherited_from: str | None = None

    @property
    def id(self) -> str:
        return f"{self.discom.id}/{self.version}"

    def params_for(self, bill_month: str | None) -> dict[str, Decimal]:
        """`params`, with the latest `params_history` entry in force for the bill month
        laid over it (guide section 7)."""
        out = dict(self.params)
        if bill_month:
            for entry in sorted(self.params_history, key=lambda e: str(e.get("from", ""))):
                if str(entry.get("from", "")) <= bill_month:
                    out.update(entry.get("params") or {})
        return out


@dataclass(frozen=True)
class Profiles:
    root: Path
    discoms: dict[str, Discom]
    versions: dict[str, tuple[ProfileVersion, ...]]  # discom id -> versions, oldest first


# loading -----------------------------------------------------------------------------------


def _tuple(x) -> tuple:
    if x is None:
        return ()
    if isinstance(x, list | tuple):
        return tuple(x)
    return (x,)


def _load_discom(folder: Path) -> Discom:
    raw = load_yaml(folder / "discom.yaml") or {}
    unknown = set(raw) - DISCOM_KEYS
    if unknown:
        raise ProfileError(f"{folder.name}/discom.yaml: unknown keys {sorted(unknown)}")
    for key in ("id", "name", "bill_type"):
        if not raw.get(key):
            raise ProfileError(f"{folder.name}/discom.yaml: missing {key}")
    if raw["id"] != folder.name:
        raise ProfileError(f"{folder.name}/discom.yaml: id does not match the folder name")
    return Discom(
        id=raw["id"],
        name=raw["name"],
        state=raw.get("state"),
        bill_type=raw["bill_type"],
        match=tuple(str(p) for p in _tuple(raw.get("match"))),
        extends=raw.get("extends"),
        label_map=tuple(_tuple(raw.get("label_map"))),
        path=folder,
    )


def _merge_rules(parent: tuple[dict, ...], child: tuple[dict, ...]) -> tuple[dict, ...]:
    """A child's rule with the same id replaces the parent's; new ones are appended."""
    by_id = {r.get("id"): r for r in parent}
    for r in child:
        by_id[r.get("id")] = r
    return tuple(by_id.values())


def _merge_version(
    base: ProfileVersion | None, discom: Discom, raw: dict, name: str
) -> ProfileVersion:
    labels = dict(base.labels) if base else {}
    for k, v in (raw.get("labels") or {}).items():
        labels[k] = tuple(_tuple(v))
    params = dict(base.params) if base else {}
    params.update(raw.get("params") or {})
    notes = dict(base.params_notes) if base else {}
    notes.update(raw.get("params_notes") or {})
    field_map = dict(base.field_map) if base else {}
    field_map.update(raw.get("field_map") or {})
    tolerances = dict(base.generic_tolerances) if base else {}
    tolerances.update(raw.get("generic_tolerances") or {})
    template = raw.get("template")
    if base and base.template and template:
        template = {**base.template, **template}
    elif base and base.template and template is None:
        template = base.template
    offset = raw.get("bill_month_offset")
    if offset is None:
        offset_t = base.bill_month_offset if base else (0, 1)
    else:
        offset_t = (int(offset[0]), int(offset[1]))
    return ProfileVersion(
        discom=discom,
        version=name,
        effective_from=str(raw.get("effective_from") or name),
        status=str(raw.get("status") or "draft"),
        layout_ids=tuple(str(x) for x in _tuple(raw.get("layout_ids"))),
        layout_match=raw.get("layout_match", base.layout_match if base else None),
        params=params,
        params_notes=notes,
        params_history=tuple(_tuple(raw.get("params_history")))
        or (base.params_history if base else ()),
        tariff_order=raw.get("tariff_order") or (base.tariff_order if base else None),
        generic_tolerances=tolerances,
        labels=labels,
        label_map=tuple(_tuple(raw.get("label_map"))) + (base.label_map if base else ()),
        field_map=field_map,
        rules=_merge_rules(base.rules if base else (), tuple(_tuple(raw.get("rules")))),
        template=template,
        tod_complete=bool(raw.get("tod_complete", base.tod_complete if base else False)),
        bill_month_offset=offset_t,
        prompt_hints=tuple(str(x) for x in _tuple(raw.get("prompt_hints"))),
        printed_units=tuple(_tuple(raw.get("printed_units")))
        or (base.printed_units if base else ()),
        inherited_from=base.id if base else None,
    )


def _version_files(folder: Path) -> list[Path]:
    versions = folder / "versions"
    if not versions.is_dir():
        return []
    return sorted(p for p in versions.glob("*.yaml") if not p.name.startswith("_"))


def load_profiles(root: Path | None = None) -> Profiles:
    root = root or profiles_dir()
    folders = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))
    discoms = {f.name: _load_discom(f) for f in folders if (f / "discom.yaml").is_file()}
    versions: dict[str, tuple[ProfileVersion, ...]] = {}

    def resolve(discom_id: str, seen: tuple[str, ...] = ()) -> tuple[ProfileVersion, ...]:
        if discom_id in versions:
            return versions[discom_id]
        if discom_id in seen:
            raise ProfileError(f"profiles: `extends` cycle through {discom_id}")
        discom = discoms[discom_id]
        parent: tuple[ProfileVersion, ...] = ()
        if discom.extends:
            if discom.extends not in discoms:
                raise ProfileError(f"{discom_id}: extends unknown discom {discom.extends}")
            parent = resolve(discom.extends, seen + (discom_id,))
        own: list[ProfileVersion] = []
        for path in _version_files(discom.path):
            raw = load_yaml(path) or {}
            errors = check_version(raw)
            if errors:
                raise ProfileError(f"{discom_id}/versions/{path.name}: " + "; ".join(errors))
            name = path.stem
            base = _pick(parent, str(raw.get("effective_from") or name)) if parent else None
            own.append(_merge_version(base, discom, raw, name))
        if not own and parent:
            # a sister discom with no versions of its own inherits the parent's, re-owned
            own = [
                _merge_version(
                    v, discom, {"effective_from": v.effective_from, "status": v.status}, v.version
                )
                for v in parent
            ]
        result = tuple(sorted(own, key=lambda v: v.effective_from))
        versions[discom_id] = result
        return result

    for discom_id in discoms:
        resolve(discom_id)
    return Profiles(root=root, discoms=discoms, versions=versions)


@lru_cache(maxsize=8)
def _cached(root: Path) -> Profiles:
    return load_profiles(root)


def profiles(root: Path | None = None) -> Profiles:
    return _cached(root or profiles_dir())


def clear_cache() -> None:
    _cached.cache_clear()
    common.cache_clear()


# selection ---------------------------------------------------------------------------------


def _pick(candidates: tuple[ProfileVersion, ...], bill_month: str | None) -> ProfileVersion:
    """The guide's rule: the latest `effective_from` on or before the bill month; `final`
    beats `draft` on a tie; older than every version -> the earliest, flagged out of range."""
    if not candidates:
        raise ProfileError("no versions")
    if bill_month is None:
        eligible = list(candidates)
    else:
        eligible = [v for v in candidates if v.effective_from <= bill_month]
    if not eligible:
        earliest = min(candidates, key=lambda v: v.effective_from)
        return _flag(earliest)
    latest = max(v.effective_from for v in eligible)
    tied = [v for v in eligible if v.effective_from == latest]
    final = [v for v in tied if v.status == "final"]
    return (final or tied)[0]


def _flag(v: ProfileVersion) -> ProfileVersion:
    from dataclasses import replace

    return replace(v, out_of_range=True)


def select_version(
    discom_id: str, bill_month: str | None, root: Path | None = None
) -> ProfileVersion:
    """The version that checks a bill of `discom_id` for `bill_month` (YYYY-MM or None)."""
    p = profiles(root)
    if discom_id not in p.discoms:
        raise ProfileError(f"unknown discom {discom_id}")
    candidates = p.versions.get(discom_id, ())
    if not candidates:
        raise ProfileError(f"{discom_id}: no versions")
    return _pick(candidates, bill_month)


def match_discom(text: str, root: Path | None = None) -> str | None:
    """The discom whose `match` pattern is found in `text`; the most specific (longest
    matched text) wins, then the longest pattern. None when nothing matches."""
    best: tuple[int, int, str] | None = None
    for discom in profiles(root).discoms.values():
        for pattern in discom.match:
            # a printed name may break across lines or carry doubled spaces: a single space
            # in a pattern matches any run of whitespace
            m = re.search(pattern.replace(" ", r"\s+"), text, re.IGNORECASE)
            if m:
                key = (len(m.group(0)), len(pattern), discom.id)
                if best is None or key > best:
                    best = key
    return best[2] if best else None


def discoms(root: Path | None = None) -> dict[str, Discom]:
    return profiles(root).discoms


# validation --------------------------------------------------------------------------------


def check_version(raw: dict) -> list[str]:
    """Problems with a version file: keys, status, params with unit and source, rules'
    expressions under the `ast` allow-list, a `tariff_order` when final. Empty when fine."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["version file is not a mapping"]
    unknown = set(raw) - VERSION_KEYS
    if unknown:
        errors.append(f"unknown keys {sorted(unknown)}")
    status = raw.get("status", "draft")
    if status not in STATUSES:
        errors.append(f"status must be one of {STATUSES}")
    eff = raw.get("effective_from")
    if eff is not None and not _MONTH.match(str(eff)):
        errors.append("effective_from must be YYYY-MM")
    if status == "final" and not raw.get("tariff_order"):
        errors.append("a final version needs tariff_order")
    params = raw.get("params") or {}
    notes = raw.get("params_notes") or {}
    if not isinstance(params, dict):
        errors.append("params must be a mapping")
        params = {}
    for name, value in params.items():
        if isinstance(value, float):
            errors.append(f"param {name} is a float")  # cannot happen through load_yaml
        elif not isinstance(value, Decimal | int):
            errors.append(f"param {name} is not a number")
        note = notes.get(name) if isinstance(notes, dict) else None
        if not isinstance(note, dict) or not note.get("unit") or not note.get("source"):
            errors.append(f"param {name} needs params_notes with unit and source")
    offset = raw.get("bill_month_offset")
    if offset is not None and not (
        isinstance(offset, list) and len(offset) == 2 and all(isinstance(x, int) for x in offset)
    ):
        errors.append("bill_month_offset must be [lo, hi] integers")
    for i, pu in enumerate(_tuple(raw.get("printed_units"))):
        errors.extend(f"printed_units {i}: {e}" for e in _check_printed_unit(pu))
    template = raw.get("template")
    if template is not None:
        if not isinstance(template, dict):
            errors.append("template must be a mapping")
        else:
            unknown_t = set(template) - TEMPLATE_KEYS
            if unknown_t:
                errors.append(f"template: unknown keys {sorted(unknown_t)}")
    rules = raw.get("rules") or []
    if not isinstance(rules, list):
        errors.append("rules must be a list")
        rules = []
    seen: set[str] = set()
    for i, rule in enumerate(rules):
        errors.extend(f"rule {i}: {e}" for e in check_rule(rule, set(params)))
        rid = rule.get("id") if isinstance(rule, dict) else None
        if rid in seen:
            errors.append(f"rule {i}: duplicate id")
        seen.add(rid)
    return errors


def check_rule(rule: Any, param_names: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(rule, dict):
        return ["not a mapping"]
    unknown = set(rule) - RULE_KEYS
    if unknown:
        errors.append(f"unknown keys {sorted(unknown)}")
    for key in ("id", "actual", "expected", "detects"):
        if not rule.get(key):
            errors.append(f"missing {key}")
    if rule.get("severity", "error") not in ("error", "warning"):
        errors.append("severity must be error or warning")
    if "tolerance" not in rule and "rel_tolerance" not in rule:
        errors.append("needs tolerance or rel_tolerance")
    for key in ("tolerance", "rel_tolerance"):
        if key in rule and not isinstance(rule[key], Decimal | int):
            errors.append(f"{key} must be a number")
    for key in ("actual", "expected"):
        text = rule.get(key)
        if isinstance(text, str):
            try:
                validate_expression(text)
            except ExpressionError as e:
                errors.append(f"{key}: {e}")
            else:
                if param_names is not None:
                    for name in referenced_params(text) - param_names:
                        errors.append(f"{key}: param {name} is not in params")
        elif text is not None:
            errors.append(f"{key} must be a string expression")
    return errors


__all__ = [
    "ALLOWED_HELPERS",
    "Discom",
    "ProfileError",
    "ProfileVersion",
    "Profiles",
    "check_rule",
    "check_version",
    "clear_cache",
    "common",
    "discoms",
    "load_profiles",
    "load_yaml",
    "match_discom",
    "profiles",
    "profiles_dir",
    "select_version",
]


def _check_printed_unit(entry) -> list[str]:
    from typing import get_args

    from billx.core.schema import Unit

    if not isinstance(entry, dict) or set(entry) != {"paths", "unit", "when"}:
        return ["needs exactly paths, unit and when"]
    errors = []
    if entry["unit"] not in get_args(Unit):
        errors.append(f"unit {entry['unit']!r} is not a known unit")
    if not isinstance(entry["paths"], list) or not entry["paths"]:
        errors.append("paths must be a non-empty list")
    try:
        re.compile(str(entry["when"]))
    except re.error:
        errors.append("when is not a valid regex")
    return errors
