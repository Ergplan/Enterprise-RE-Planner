"""Profiles: loading, Decimal YAML, inheritance, select_version, match_discom, check_version,
and the template folder."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from billx.reader.identify import profiles as P

ROOT = Path(__file__).resolve().parents[2] / "profiles"


def _write(root: Path, discom: str, body: str, versions: dict[str, str] | None = None) -> None:
    (root / discom / "versions").mkdir(parents=True, exist_ok=True)
    (root / discom / "discom.yaml").write_text(body)
    for name, text in (versions or {}).items():
        (root / discom / "versions" / f"{name}.yaml").write_text(text)


DISCOM = """
id: {id}
name: {name}
state: Nowhere
bill_type: electricity
match: [{match}]
{extra}
"""
VERSION = """
status: {status}
params: {{ed_rate_kvah: 0.40, energy_rate_kvah: 7.30}}
params_notes:
  ed_rate_kvah: {{unit: INR/kVAh, source: test}}
  energy_rate_kvah: {{unit: INR/kVAh, source: test}}
{extra}
rules:
  - id: {rule_id}
    description: ED
    severity: error
    tolerance: 1
    actual: item("Electricity Duty")
    expected: param("ed_rate_kvah") * meter("Total", quantity="kVAh")
    detects: Rs 1
"""


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "_common.yaml").write_text((ROOT / "_common.yaml").read_text())
    (tmp_path / "_template").mkdir()
    _write(
        tmp_path,
        "base",
        DISCOM.format(
            id="base",
            name="Base Nigam",
            match='"\\\\bBASE\\\\b", "Base Nigam"',
            extra='label_map:\n  - {pattern: "special", code: cess}',
        ),
        {
            "2024-04": VERSION.format(
                status="draft", extra="tod_complete: true", rule_id="base.ed"
            ),
            "2025-04": VERSION.format(
                status="final",
                extra=(
                    'tariff_order: {regulator: X, number: "1"}\n'
                    'label_map:\n  - {pattern: "odd", code: fppca}'
                ),
                rule_id="base.ed",
            ),
            "2025-04b": VERSION.format(
                status="draft", extra='effective_from: "2025-04"', rule_id="base.ed"
            ),
        },
    )
    _write(
        tmp_path,
        "child",
        DISCOM.format(id="child", name="Child Nigam", match='"Child Nigam"', extra="extends: base"),
        {
            "2025-06": VERSION.format(
                status="draft",
                extra=(
                    "params: {ed_rate_kvah: 0.50}\n"
                    "params_notes: {ed_rate_kvah: {unit: INR/kVAh, source: t}}"
                ),
                rule_id="child.extra",
            )
        },
    )
    _write(
        tmp_path,
        "orphan",
        DISCOM.format(id="orphan", name="Orphan Nigam", match='"Orphan"', extra="extends: base"),
    )
    monkeypatch.setenv("BILLX_PROFILES_DIR", str(tmp_path))
    P.clear_cache()
    yield tmp_path
    P.clear_cache()


def test_repository_profiles_load_as_drafts_with_decimal_params():
    P.clear_cache()
    p = P.profiles(ROOT)
    assert {"avvnl", "pvvnl"} <= set(p.discoms)
    assert len(p.discoms) == 11  # Stage 3.2: a draft discom.yaml for every discom in the sample
    for discom_id, name in (
        ("avvnl", "Ajmer Vidyut Vitran Nigam Limited"),
        ("pvvnl", "Paschimanchal Vidyut Vitran Nigam Limited"),
    ):
        d = p.discoms[discom_id]
        assert d.name == name and d.bill_type == "electricity" and d.extends is None
        v = P.select_version(discom_id, "2026-01", ROOT)
        assert v.status == "draft" and v.version == "2025-01" and not v.out_of_range
        assert v.tod_complete and v.rules and v.params_notes.keys() == v.params.keys()
        assert all(isinstance(x, Decimal) for x in v.params.values())
    assert P.select_version("avvnl", "2026-01", ROOT).params["energy_rate_kvah"] == Decimal("7.30")
    assert P.select_version("avvnl", "2026-01", ROOT).bill_month_offset == (0, 0)
    assert P.select_version("pvvnl", "2026-01", ROOT).bill_month_offset == (0, 1)
    assert P.select_version("pvvnl", "2026-01", ROOT).params["demand_rate_kva"] == Decimal("300.00")


def test_match_discom_english_and_hindi_most_specific_wins():
    P.clear_cache()
    assert P.match_discom("AJMER VIDYUT VITRAN NIGAM LIMITED bill", ROOT) == "avvnl"
    assert P.match_discom("अजमेर विद्युत वितरण निगम लिमिटेड", ROOT) == "avvnl"
    assert P.match_discom("पश्चिमांचल विद्युत वितरण निगम लि.", ROOT) == "pvvnl"
    assert P.match_discom("Bill cum notice PVVNL Meerut", ROOT) == "pvvnl"
    assert P.match_discom("Some Other Board", ROOT) is None
    assert P.match_discom("AVVNL", ROOT) == "avvnl"
    assert P.match_discom("XAVVNLX", ROOT) is None  # word boundary


def test_select_version_rules(root):
    assert P.select_version("base", "2025-03").version == "2024-04"
    tie = P.select_version("base", "2025-04")
    assert tie.version == "2025-04" and tie.status == "final"  # final beats draft on a tie
    assert P.select_version("base", "2026-01").version == "2025-04"
    old = P.select_version("base", "2023-01")
    assert old.version == "2024-04" and old.out_of_range
    assert not P.select_version("base", "2024-04").out_of_range
    assert P.select_version("base", None).version == "2025-04"
    with pytest.raises(P.ProfileError):
        P.select_version("nobody", "2025-01")


def test_inheritance_through_extends(root):
    child = P.select_version("child", "2025-07")
    assert child.inherited_from == "base/2025-04"
    assert child.params["ed_rate_kvah"] == Decimal("0.50")  # overridden
    assert child.params["energy_rate_kvah"] == Decimal("7.30")  # inherited
    assert [r["id"] for r in child.rules] == ["base.ed", "child.extra"]
    assert child.label_map[0]["pattern"] == "odd"  # the parent's label_map comes along
    assert child.tariff_order == {"regulator": "X", "number": "1"}
    assert child.discom.extends == "base" and child.discom.label_map == ()
    early = P.select_version("child", "2025-05")  # older than every child version
    assert early.version == "2025-06" and early.out_of_range
    orphan = P.select_version("orphan", "2026-01")
    assert (
        orphan.discom.id == "orphan"
        and orphan.version == "2025-04"
        and orphan.inherited_from == "base/2025-04"
    )


def test_yaml_numbers_are_decimals_never_floats(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text("a: 7.30\nb: 1.0e+3\nc: 5\nd: [0.1, 0.2]\n")
    data = P.load_yaml(f)
    assert data["a"] == Decimal("7.30") and isinstance(data["a"], Decimal)
    assert data["b"] == Decimal("1e3") and isinstance(data["b"], Decimal)
    assert data["c"] == 5 and isinstance(data["c"], int)
    assert sum(data["d"]) == Decimal("0.3")
    f.write_text("a: .nan\n")
    with pytest.raises(P.ProfileError):
        P.load_yaml(f)


def test_check_version_errors():
    good = {
        "status": "draft",
        "params": {"x": Decimal("1")},
        "params_notes": {"x": {"unit": "INR", "source": "t"}},
        "rules": [
            {
                "id": "r",
                "severity": "error",
                "tolerance": 1,
                "actual": "param('x')",
                "expected": "1",
                "detects": "d",
            }
        ],
    }
    assert P.check_version(good) == []
    e = P.check_version({**good, "bogus": 1, "status": "live", "effective_from": "2025"})
    assert (
        any("unknown keys" in x for x in e)
        and any("status" in x for x in e)
        and any("effective_from" in x for x in e)
    )
    assert P.check_version({**good, "status": "final"}) == ["a final version needs tariff_order"]
    assert P.check_version({**good, "params_notes": {}}) == [
        "param x needs params_notes with unit and source"
    ]
    assert P.check_version({**good, "params": {"x": "7"}})[0].startswith("param x is not a number")
    assert any(
        "not in params" in x
        for x in P.check_version({**good, "rules": [{**good["rules"][0], "actual": "param('zz')"}]})
    )
    assert any(
        "missing detects" in x
        for x in P.check_version(
            {**good, "rules": [{k: v for k, v in good["rules"][0].items() if k != "detects"}]}
        )
    )
    assert any(
        "tolerance" in x
        for x in P.check_version(
            {**good, "rules": [{k: v for k, v in good["rules"][0].items() if k != "tolerance"}]}
        )
    )
    assert any("duplicate id" in x for x in P.check_version({**good, "rules": good["rules"] * 2}))
    assert any(
        "bill_month_offset" in x for x in P.check_version({**good, "bill_month_offset": [0]})
    )
    assert any("template" in x for x in P.check_version({**good, "template": {"lines": []}}))
    assert P.check_version("nope") == ["version file is not a mapping"]


def test_bad_profile_is_refused_at_load(root):
    (root / "base" / "versions" / "2026-01.yaml").write_text(
        "status: draft\nrules:\n"
        "  - {id: x, actual: 'open(1)', expected: '1', tolerance: 1, detects: d}\n"
    )
    P.clear_cache()
    with pytest.raises(P.ProfileError):
        P.profiles()


def test_template_folder_is_skipped_but_valid():
    P.clear_cache()
    assert "_template" not in P.profiles(ROOT).discoms
    raw = P.load_yaml(ROOT / "_template" / "versions" / "YYYY-MM.yaml")
    assert P.check_version(raw) == []
    discom = P._load_discom(ROOT / "_template")
    assert discom.id == "_template" and discom.match


def test_every_repository_version_file_passes_check_version():
    for path in ROOT.glob("*/versions/*.yaml"):
        assert P.check_version(P.load_yaml(path)) == [], path


def test_match_tolerates_line_breaks_and_doubled_spaces_in_a_printed_name():
    assert P.match_discom("AJMER VIDYUT\nVITRAN  NIGAM LIMITED") == "avvnl"
    assert P.match_discom("Paschimanchal\n  Vidyut Vitran Nigam Ltd") == "pvvnl"


def test_a_scan_that_cuts_the_first_letters_still_names_pvvnl():
    assert P.match_discom("CHIMANCHAL VIDYUT VITRAN NIGAM LIMITED") == "pvvnl"
    assert P.match_discom("MADHYANCHAL VIDYUT VITRAN NIGAM LIMITED") == "mvvnl"


def test_printed_units_are_checked():
    ok = {"paths": ["open_access.re_kwh"], "unit": "kVAh", "when": "open access adjustment"}
    assert P.check_version({"status": "draft", "printed_units": [ok]}) == []
    errors = P.check_version(
        {"status": "draft", "printed_units": [{**ok, "unit": "MWh"}, {**ok, "when": "("}, {}]}
    )
    assert len(errors) == 3 and all(e.startswith("printed_units") for e in errors)


def test_pvvnl_keeps_open_access_units_as_printed_in_kvah():
    from billx.core.schema import make_value
    from billx.reader.pipeline import _printed_units

    version = load_profiles_version("pvvnl")
    values = [
        make_value("open_access.re_kwh", "number", (), unit="kWh"),
        make_value("energy.kwh", "number", (), unit="kWh"),
    ]
    adjusted = _printed_units(values, version, "OPEN ACCESS ADJUSTMENT BILL")
    assert [v.unit for v in adjusted] == ["kVAh", "kWh"]
    assert [v.unit for v in _printed_units(values, version, "an ordinary bill")] == ["kWh", "kWh"]


def load_profiles_version(discom: str):
    return P.load_profiles().versions[discom][-1]
