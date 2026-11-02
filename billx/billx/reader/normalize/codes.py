"""The element catalogue (build prompt 5.7): one closed list of codes in
`profiles/_common.yaml`, and `code_for`, which maps a printed line to a code through the
label maps, most specific first: the profile version's, then the discom's, then the common
one; a line no pattern matches is `other`. Patterns are case-insensitive searches on
"<group> :: <label>".
"""

from __future__ import annotations

import re
from functools import lru_cache

from billx.reader.identify.profiles import ProfileVersion, common

OTHER = "other"


@lru_cache(maxsize=256)
def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


def catalogue() -> list[str]:
    return list(common().get("codes") or [])


def _lookup(label_map, key: str) -> str | None:
    for entry in label_map or ():
        if _rx(str(entry["pattern"])).search(key):
            return str(entry["code"])
    return None


def code_for(group: str | None, label: str, version: ProfileVersion | None = None) -> str:
    key = f"{group or ''} :: {label}"
    maps = []
    if version is not None:
        maps.append(version.label_map)
        maps.append(version.discom.label_map)
    maps.append(common().get("label_map") or ())
    codes = set(catalogue())
    for label_map in maps:
        code = _lookup(label_map, key)
        if code is not None:
            return code if code in codes else OTHER
    return OTHER


__all__ = ["OTHER", "catalogue", "code_for"]
