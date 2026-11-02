"""config/guaranteed_fields.yaml carries contract 1.0's section 6 exactly (paths and
required flags), plus the 6.4 additions marked contract 1.1."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (ROOT / "contract/esgos-1.0/contract.md").read_text()
FIELDS = yaml.safe_load((ROOT / "config/guaranteed_fields.yaml").read_text())


def _contract_table(heading: str) -> dict[str, bool]:
    """{path: required} from the contract's table under **Electricity** or **Gas**. An
    array row (`readings[]`: `register`, ...) contributes the array path only."""
    start = CONTRACT.index(f"**{heading}**")
    end = (
        CONTRACT.index("**Gas**", start)
        if heading == "Electricity"
        else CONTRACT.find("\n## ", start)
    )
    out = {}
    for line in CONTRACT[start:end].splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        paths = re.findall(r"`([^`]+)`", cells[0].split(":")[0])
        for p in paths:
            out[p] = cells[2].startswith("required")
    return out


def _yaml_paths(kind: str) -> dict[str, bool]:
    out = {}
    for f in FIELDS[kind]:
        if f.get("contract") == "1.1":
            continue
        if f["type"] == "array":
            base = f["path"][:-2]
            out[f["path"]] = False
            for item in f["items"]:
                out[f"{base}[].{item['path']}"] = False
        else:
            out[f["path"]] = bool(f["required"])
    return out


def test_electricity_matches_contract_section_6():
    contract = _contract_table("Electricity")
    ours = {p: r for p, r in _yaml_paths("electricity").items() if "[]." not in p}
    assert set(contract) == set(ours)
    for p, req in contract.items():
        assert ours[p] == req, p


def test_gas_matches_contract_section_6():
    contract = _contract_table("Gas")
    ours = _yaml_paths("gas")
    assert set(contract) == set(ours)
    for p, req in contract.items():
        assert ours[p] == req, p


def test_additions_are_exactly_section_6_4():
    added = {f["path"] for f in FIELDS["electricity"] if f.get("contract") == "1.1"}
    assert added == {
        "consumer.name",
        "period.due_date",
        "totals.current_charges",
        "totals.arrears",
        "charges.by_code[]",
        "tariff.category",
        "open_access.re_kwh",
        "open_access.non_re_kwh",
        "open_access.banked_kwh",
        "green_tariff.kwh",
        "energy.billed_units",
        "totals.due_date_rebate",
    }
