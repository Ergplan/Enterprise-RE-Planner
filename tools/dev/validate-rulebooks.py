#!/usr/bin/env python3
"""Validate every YAML under packages/rulebooks/ against its family schema. Used by the watcher and CI."""
import glob, json, os, sys
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SDIR = os.path.join(ROOT, "packages", "rulebooks", "schemas")

def main() -> int:
    schemas = {os.path.basename(p): json.load(open(p)) for p in glob.glob(f"{SDIR}/*.json")}
    reg = Registry()
    for name, s in schemas.items():
        Draft202012Validator.check_schema(s)
        reg = reg.with_resource(name, Resource.from_contents(s))
    bad = 0
    for f in glob.glob(os.path.join(ROOT, "packages", "rulebooks", "**", "*.yaml"), recursive=True):
        d = yaml.safe_load(open(f))
        if not isinstance(d, dict) or "family" not in d or "rows" not in d:
            continue  # golden test files and the jurisdiction list are checked by the API tests
        v = Draft202012Validator(schemas[f"{d['family']}.schema.json"], registry=reg)
        for i, row in enumerate(d.get("rows", [])):
            for e in v.iter_errors(row):
                bad += 1
                print(f"{os.path.relpath(f, ROOT)} row {i} {list(e.path)}: {e.message}")
    print("rulebooks: OK" if not bad else f"rulebooks: {bad} error(s)")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
